"""Backend contract and worker tests. Providers/storage/DB are never contacted."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from engine import assembler, quiz, quiz_motion, script, video


def source(mode="motion"):
    return {"title": "Motion backend test", "niche": "culture", "account": "test",
            "content_format": "quiz", "aspect_ratio": "9:16", "platform": "tiktok",
            "quiz": {"presentation": mode, "topic": "Espace", "illustrations": False,
                     "sound_effects": "off", "questions": [{"question": "Quelle planète ?",
                         "choices": ["Mercure", "Mars"], "correct_choice": 0,
                         "explanation": "Mercure est la bonne réponse.", "countdown_seconds": 1}]}}


class MotionTimelineTests(unittest.TestCase):
    def test_real_durations_and_cover_define_reflection_and_reveal(self):
        data = source()
        data["quiz"]["cover"] = {"enabled": True, "title": "Espace", "duration_seconds": .8}
        data = script.normalize_script(data)
        report = quiz_motion.build_timeline(data, [2, 4.25, 3, 1])
        self.assertEqual(report["totalDurationSeconds"], 11.05)
        self.assertEqual(report["scenes"][1]["reflectionStartSeconds"], 6.05)
        self.assertEqual(report["scenes"][2]["startSeconds"], 7.05)
        self.assertEqual(report["additionalProviderCalls"], 0)
        self.assertIsNone(report["renderCostUsd"])

    def test_unmeasured_or_invalid_durations_are_not_silently_truncated(self):
        data = script.normalize_script(source())
        for durations in ([1], [1, float("nan"), 1, 1], [1, .5, 1, 1], [1, float("inf"), 1, 1]):
            with self.subTest(durations=durations), self.assertRaises(ValueError):
                quiz_motion.build_timeline(data, durations)

    def test_compiled_blocks_cannot_override_answers_or_reflection(self):
        for key, value in (("quiz_correct_choice", 1), ("quiz_choices", ["Wrong", "Other"]),
                           ("hold_after_seconds", 900), ("quiz_question_number", 7)):
            data = script.normalize_script(source())
            data["blocks"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                script.normalize_script(data)
        data = script.normalize_script(source())
        data["blocks"][1], data["blocks"][2] = data["blocks"][2], data["blocks"][1]
        with self.assertRaises(ValueError):
            script.normalize_script(data)


class WorkerMotionTests(unittest.TestCase):
    def harness(self, data, failure=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        def stub(target, **kwargs):
            return stack.enter_context(patch(target, **kwargs))
        stub("engine.assembler.db.get_service_client", return_value=Mock())
        stub("engine.assembler.repo.get_script", return_value=deepcopy(data))
        reserve = stub("engine.assembler.repo.reserve_generation_credit", return_value=True)
        refund = stub("engine.assembler.repo.refund_generation_credit")
        update = stub("engine.assembler.repo.update_content_item")
        stub("engine.assembler.repo.mark_generation_completed")
        stub("engine.assembler.events.organization_id_of", return_value="organization")
        events = stub("engine.assembler.events.record")
        stub("engine.assembler.moderation.check_script")
        stub("engine.assembler.asset_store.configure")
        stub("engine.assembler.asset_store.stats", return_value={})
        stub("engine.assembler.asset_store.finish")
        stub("engine.assembler.asset_store.reset")
        stub("engine.assembler.originality.originality_enabled", return_value=False)
        stub("engine.assembler.versions.next_version_number", return_value=2)
        version = stub("engine.assembler.versions.record_version", return_value="version-two")
        stub("engine.assembler.versions.upload_captions_safe", return_value=None)
        publish = stub("engine.assembler._publish_video", return_value="https://example.invalid/video-v2.mp4")
        stub("engine.assembler._publish_poster", return_value=None)
        stub("engine.assembler._quality_fields", return_value={})
        stub("engine.assembler._store_creative_quality_shadow")
        stub("engine.assembler.publish_pack.write_pack", return_value={})

        def generate(compiled, *_args, **_kwargs):
            if failure:
                raise failure
            report = quiz_motion.build_timeline(compiled, [1, 2, 1, 1])
            quiz_motion.attach_report(compiled, report)
            return "video.mp4", Path("output-test"), None

        render = stub("engine.assembler._generate", side_effect=generate)
        return reserve, refund, update, version, events, publish, render

    def test_worker_persists_mode_and_report_in_item_and_immutable_version(self):
        for mode in ("classic", "motion"):
            with self.subTest(mode=mode):
                reserve, refund, update, version, events, publish, render = self.harness(source(mode))
                assembler.run_for_content_item("item")
                reserve.assert_called_once()
                refund.assert_not_called()
                saved = update.call_args.kwargs["script"]
                self.assertEqual(saved["quiz"]["presentation"], mode)
                self.assertEqual(saved["generationMetadata"]["quizPresentation"]["mode"], mode)
                self.assertEqual(version.call_args.kwargs["script"], saved)
                self.assertEqual(events.call_args.kwargs["quiz_presentation"]["mode"], mode)
                self.assertEqual(publish.call_args.kwargs["version"], 2)

    def test_invalid_choice_fails_before_credit_or_render(self):
        data = source("invalid")
        reserve, refund, update, version, events, publish, render = self.harness(data)
        with self.assertRaises(ValueError):
            assembler.run_for_content_item("item")
        reserve.assert_not_called()
        render.assert_not_called()
        publish.assert_not_called()

    def test_stale_compiled_answers_fail_before_credit(self):
        data = script.normalize_script(source())
        data["blocks"][2]["quiz_correct_choice"] = 1
        reserve, refund, update, version, events, publish, render = self.harness(data)
        with self.assertRaisesRegex(ValueError, "correspondent"):
            assembler.run_for_content_item("item")
        reserve.assert_not_called()
        render.assert_not_called()

    def test_render_failure_refunds_and_never_publishes(self):
        reserve, refund, update, version, events, publish, render = self.harness(source(), RuntimeError("render failed"))
        with self.assertRaisesRegex(RuntimeError, "render failed"):
            assembler.run_for_content_item("item")
        reserve.assert_called_once()
        refund.assert_called_once()
        publish.assert_not_called()
        version.assert_not_called()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class RealMotionRenderTests(unittest.TestCase):
    def test_pipeline_renders_then_reuses_video_without_provider_calls(self):
        # A synthetic WAV replaces ElevenLabs; actual duration probing,
        # silence padding, ASS rendering and FFmpeg assembly are exercised.
        def synthesize(text, voice, out_path, _key):
            target = Path(out_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(target), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b"\0\0" * 12000)
            return [{"text": text, "start": 0.0, "end": .5}]

        data = script.normalize_script(source())
        with tempfile.TemporaryDirectory(prefix="qmotion-") as folder, \
             patch.dict(os.environ, {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}, clear=True), \
             patch("engine.assembler.voices.resolve_voice", return_value="test-voice"), \
             patch("engine.assembler.tts.synthesize_with_timestamps", side_effect=synthesize) as provider, \
             patch("engine.assembler.visuals.fetch_block_images") as images, \
             patch.dict(video.RESOLUTIONS, {"9:16": "360x640"}):
            path, work, metrics = assembler._generate(data, folder, None)
            self.assertGreater(Path(path).stat().st_size, 0)
            images.assert_not_called()
            report = data["generationMetadata"]["quizPresentation"]
            self.assertEqual(report["mode"], "motion")
            self.assertGreaterEqual(report["renderSeconds"], 0)
            self.assertEqual(report, json.loads((work / "quiz-presentation.json").read_text(encoding="utf-8")))
            self.assertIn("quiz_presentation", metrics)
            provider.reset_mock()
            cached_data = script.normalize_script(source())
            cached_path, _, cached_metrics = assembler._generate(cached_data, folder, None)
            self.assertEqual(path, cached_path)
            self.assertIsNone(cached_metrics)
            provider.assert_not_called()
            self.assertEqual(cached_data["generationMetadata"]["quizPresentation"], {**report, "reusedFinalVideo": True})
            (work / "quiz-presentation.json").write_text("invalid json", encoding="utf-8")
            missing_report_data = script.normalize_script(source())
            assembler._generate(missing_report_data, folder, None)
            missing = missing_report_data["generationMetadata"]["quizPresentation"]
            self.assertTrue(missing["reusedFinalVideo"])
            self.assertIsNone(missing["renderSeconds"])
            self.assertEqual(missing["timingSource"], "unavailable")
            provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
