"""Branchement de l'Explainer dans la chaîne de rendu : choix du style, voice_report, intégration avec Explainer simulé.

Aucun appel réseau : la voix (ElevenLabs) et `pipeline.generate` sont simulés ; ffmpeg est réel.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from engine import assembler, video, visuals
from engine.explainer import integration, timeline

BLOCKS = [
    {"role": "hook", "text": "Pourquoi le ciel est bleu ?"},
    {"role": "point", "text": "La lumière du soleil contient toutes les couleurs."},
    {"role": "cta", "text": "Abonne-toi pour la suite."},
]


def script(**extra):
    return {"title": "Le ciel bleu", "niche": "science", "account": "test", "platform": "tiktok", "aspect_ratio": "9:16",
            "visual_style": "explainer", "caption_style": "off", "blocks": [dict(b) for b in BLOCKS], **extra}


class StyleChoiceTests(unittest.TestCase):
    def test_prefers_explainer_only_for_the_explainer_id(self):
        self.assertTrue(visuals.prefers_explainer({"visual_style": "explainer"}))
        self.assertTrue(visuals.prefers_explainer({"visual_style": " Explainer "}))
        for other in ("motion_graphics", "kinetic_typography", "cinematic_real", "", None):
            self.assertFalse(visuals.prefers_explainer({"visual_style": other}), other)
        self.assertFalse(visuals.prefers_explainer({}))

    def test_explainer_does_not_capture_other_styles(self):
        # `prefers_motion_graphics` reste inchangée : l'exclusivité est portée par l'assembleur.
        self.assertTrue(visuals.prefers_motion_graphics("motion_graphics", ""))
        self.assertFalse(visuals.prefers_motion_graphics("explainer", ""))


class VoiceReportTests(unittest.TestCase):
    def test_offsets_are_cumulative_and_words_absolute(self):
        durations = [2.0, 3.5, 1.0]   # le bloc 2 inclut 0,5 s de silence ajouté à l'audio
        words = [[{"text": "Pourquoi", "start": 0.1, "end": 0.6}, {"text": "bleu", "start": 1.2, "end": 1.7}],
                 [{"text": "La", "start": 0.0, "end": 0.2}],
                 [{"text": "Abonne-toi", "start": 0.0, "end": 0.8}]]
        report = integration.voice_report_from_blocks(BLOCKS, durations, words)
        self.assertEqual([line["start"] for line in report["lines"]], [0.0, 2.0, 5.5])
        self.assertEqual([line["text"] for line in report["lines"]], [b["text"] for b in BLOCKS])
        self.assertEqual([(w["text"], w["start"], w["end"]) for w in report["words"]],
                         [("Pourquoi", 0.1, 0.6), ("bleu", 1.2, 1.7), ("La", 2.0, 2.2), ("Abonne-toi", 5.5, 6.3)])
        self.assertEqual(report["durationSeconds"], 6.5)

    def test_report_is_readable_by_the_explainer_timeline(self):
        words = [[{"text": "a", "start": 0.0, "end": 0.4}], [{"text": "b", "start": 0.1, "end": 0.5}], [{"text": "c", "start": 0.2, "end": 0.6}]]
        report = integration.voice_report_from_blocks(BLOCKS, [1.0, 2.0, 1.5], words)
        narration, timeline_words = timeline.narration_from_report(report)
        self.assertEqual([start for start, _ in narration], [0.0, 1.0, 3.0])
        self.assertEqual([w["line"] for w in timeline_words], [0, 1, 2])

    def test_mismatched_inputs_and_empty_text_fail_explicitly(self):
        with self.assertRaises(integration.ExplainerError):
            integration.voice_report_from_blocks(BLOCKS, [1.0], [[]])
        with self.assertRaises(integration.ExplainerError):
            integration.voice_report_from_blocks([{"text": "  "}], [1.0], [[]])


def _wav(path, seconds=1.0):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\0\0" * int(24000 * seconds))


def fake_pipeline(calls, *, fallbacks=None, fail=None):
    """Remplace `engine.explainer.pipeline` : écrit un vrai MP4 (couleur unie) et un rapport, sans réseau."""
    def generate(topic, out_dir, **kwargs):
        calls.append({"topic": topic, **kwargs})
        if fail:
            raise fail
        out = Path(out_dir)
        total = kwargs["voice_report"]["durationSeconds"] + 1.2
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x203040:s=360x640:r=30:d={total}",
                        "-f", "lavfi", "-i", f"sine=frequency=440:duration={total}", "-shortest", "-pix_fmt", "yuv420p", str(out / "explainer.mp4")], check=True)
        report = {"topic": topic, "mode": kwargs["mode"], "timingsAreEstimated": False, "runtimeVersion": "0.1.0",
                  "plans": [{"id": "p1", "ok": True}, {"id": "p2", "ok": False}], "fallbacks": fallbacks or [],
                  "unresolvedAnchors": [], "steps": {"director": 3.0, "render": 12.3, "totalSeconds": 30.5},
                  "spend": {"totalUsd": 0.42, "limitUsd": 1.2, "unknownCost": False}, "render": {"chromium": "test"}}
        if kwargs["use_critic"]:
            report["critic"] = {"videoAverage": 3.0}
        return report
    return types.SimpleNamespace(generate=generate)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class AssemblerIntegrationTests(unittest.TestCase):
    def run_generate(self, data, pipeline, extra_env=None):
        synthesized = []

        def synthesize(text, voice, out_path, _key):
            synthesized.append(text)
            _wav(out_path, 1.0)
            return [{"text": text.split()[0], "start": 0.0, "end": 0.4}, {"text": text.split()[-1], "start": 0.5, "end": 0.9}]

        keep = {k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}}
        with tempfile.TemporaryDirectory(prefix="explainer-") as folder, \
             patch.dict(os.environ, {**keep, **(extra_env or {})}, clear=True), \
             patch.dict(sys.modules, {"engine.explainer.pipeline": pipeline}), \
             patch("engine.explainer.pipeline", pipeline, create=True), \
             patch("engine.assembler.voices.resolve_voice", return_value="test-voice"), \
             patch("engine.assembler.tts.synthesize_with_timestamps", side_effect=synthesize), \
             patch("engine.assembler.visuals.fetch_block_images", return_value=([None] * 3, [], [], [])) as images, \
             patch("engine.assembler.visuals.fetch_motion_graphics_clips", return_value=[None] * 3) as motion, \
             patch("engine.assembler.visuals.fetch_kinetic_typography_clips", return_value=[None] * 3) as kinetic, \
             patch.dict(video.RESOLUTIONS, {"9:16": "360x640"}):
            try:
                result = assembler._generate(data, folder, None)
            finally:
                self.other_visuals = (images, motion, kinetic)
            path, work, metrics = result
            self.assertGreater(Path(path).stat().st_size, 0)
            self.last = {"path": path, "work": Path(work), "metrics": metrics, "synthesized": synthesized,
                         "ass": (Path(work) / "captions.ass").read_text(encoding="utf-8")}
            return self.last

    def test_explainer_script_renders_with_real_voice_timings_and_reports_cost(self):
        calls = []
        out = self.run_generate(script(), fake_pipeline(calls, fallbacks=[{"plan": "p2", "reason": ["x"], "text": "t"}]))
        self.assertEqual(len(calls), 1)
        call = calls[0]
        # La narration est celle du script, les timings sont mesurés, la voix n'est pas remixée par l'Explainer.
        self.assertEqual(call["lines"], [b["text"] for b in BLOCKS])
        self.assertEqual(call["voice_report"]["timingSource"], "measured")
        self.assertEqual([line["start"] for line in call["voice_report"]["lines"]], [0.0, 1.0, 2.0])
        self.assertIsNone(call["voice_wav"])
        self.assertEqual((call["mode"], call["use_critic"]), ("templates", False))
        # Aucun autre style n'a été sollicité, la voix a été synthétisée une fois par bloc.
        for fetcher in self.other_visuals:
            fetcher.assert_not_called()
        self.assertEqual(len(out["synthesized"]), 3)
        # Style de sous-titres « off » : aucune bande ajoutée.
        self.assertNotIn("Dialogue:", out["ass"])
        summary = out["metrics"]["explainer"]
        self.assertEqual((summary["mode"], summary["plans"], summary["fallbacks"], summary["timingSource"]), ("templates", 2, 1, "measured"))
        self.assertEqual((summary["llmCostUsd"], summary["renderSeconds"], summary["sfxIncluded"]), (0.42, 12.3, False))
        with patch.dict(os.environ, {"ELEVENLABS_USD_PER_1K_CHARS": "0.18"}):
            cost = assembler._generation_cost_report(out["metrics"])
        self.assertEqual(cost["explainer"]["cost"], 0.42)
        self.assertGreaterEqual(cost["totalEstimatedCost"], 0.42)
        self.assertNotIn("explainer", cost["missingRates"])

    def test_settings_come_from_the_environment(self):
        calls = []
        self.run_generate(script(), fake_pipeline(calls), {"EXPLAINER_MODE": "code", "EXPLAINER_USE_CRITIC": "true"})
        self.assertEqual((calls[0]["mode"], calls[0]["use_critic"]), ("code", True))

    def test_failure_is_explicit_and_never_falls_back_to_another_style(self):
        calls = []
        with self.assertRaisesRegex(integration.ExplainerError, "Chromium absent"):
            self.run_generate(script(), fake_pipeline(calls, fail=RuntimeError("Chromium absent")))
        for fetcher in self.other_visuals:
            fetcher.assert_not_called()

    def test_non_vertical_aspect_ratio_is_refused(self):
        calls = []
        with self.assertRaisesRegex(integration.ExplainerError, "9:16"):
            self.run_generate(script(aspect_ratio="16:9"), fake_pipeline(calls))
        self.assertEqual(calls, [])

    def test_other_styles_do_not_touch_the_explainer(self):
        for style, fetcher_index in (("motion_graphics", 1), ("flat_color", 2), ("cinematic_real", 0)):
            with self.subTest(style=style):
                calls = []
                with patch("engine.explainer.integration.generate_clips") as clips:
                    self.run_generate(script(visual_style=style), fake_pipeline(calls))
                    clips.assert_not_called()
                self.assertEqual(calls, [])
                self.other_visuals[fetcher_index].assert_called_once()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class ReuseTests(unittest.TestCase):
    def test_same_inputs_reuse_the_rendered_explainer(self):
        data = script()
        words = [[{"text": "a", "start": 0.0, "end": 0.4}]] * 3
        calls = []
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            first, summary = integration.generate_clips(data, [1.0, 1.0, 1.0], words, folder, generate_fn=fake_pipeline(calls).generate, log=lambda *_: None)
            second, again = integration.generate_clips(data, [1.0, 1.0, 1.0], words, folder, generate_fn=fake_pipeline(calls).generate, log=lambda *_: None)
            self.assertEqual(len(calls), 1)
            self.assertEqual((summary["reused"], again["reused"]), (False, True))
            self.assertEqual(len(first), 3)
            self.assertEqual(first, second)
            # Entrées différentes (texte voix/mots) : nouveau rendu.
            integration.generate_clips(data, [1.0, 1.0, 1.0], [[{"text": "z", "start": 0.0, "end": 0.4}]] * 3, folder,
                                       generate_fn=fake_pipeline(calls).generate, log=lambda *_: None)
            self.assertEqual(len(calls), 2)

    def test_estimated_timings_are_rejected(self):
        def generate(topic, out_dir, **kwargs):
            report = fake_pipeline([]).generate(topic, out_dir, **kwargs)
            report["timingsAreEstimated"] = True
            return report
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(integration.ExplainerError, "estimés"):
            integration.generate_clips(script(), [1.0, 1.0, 1.0], [[]] * 3, folder, generate_fn=generate, log=lambda *_: None)


class QueueDetectionTests(unittest.TestCase):
    def test_only_explainer_scripts_trigger_the_install(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        try:
            import queue_needs_explainer as detector
        finally:
            sys.path.pop(0)
        self.assertTrue(detector.is_explainer({"visual_style": "explainer"}))
        for other in ({"visual_style": "motion_graphics"}, {}, None, "explainer", {"visual_style": None}):
            self.assertFalse(detector.is_explainer(other), other)


if __name__ == "__main__":
    unittest.main()
