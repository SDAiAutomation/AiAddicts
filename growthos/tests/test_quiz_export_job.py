"""Job worker des exports de chapitre : cache audio, isolation, échecs sans effet sur le master."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import quiz_export_job, quiz_shorts, repo
from engine.quiz import compile_quiz
from tests.test_quiz_chapters import script


class Chain:
    """Minimal supabase-py query double returning canned data for any chain."""
    def __init__(self, data=None, log=None, name=""):
        self.data, self.log, self.name = data, log if log is not None else [], name
    def __getattr__(self, attr):
        def call(*args, **kwargs):
            self.log.append((self.name, attr, args, kwargs))
            return self
        return call
    def execute(self):
        return mock.Mock(data=self.data)


class Client:
    def __init__(self, tables):
        self.tables, self.log = tables, []
    def table(self, name):
        return Chain(self.tables.get(name), self.log, name)
    def rpc(self, name, *a):
        return Chain(self.tables.get("rpc:" + name), self.log, "rpc:" + name)


class StoragePathTests(unittest.TestCase):
    def test_only_fixed_names_are_accepted(self):
        self.assertEqual(quiz_export_job.export_storage_path("abc", 3, "quiz_hard.mp4"), "abc/shorts/v3/quiz_hard.mp4")
        self.assertEqual(quiz_export_job.export_storage_path("abc", None, "quiz_easy_part2.mp4"), "abc/shorts/v0/quiz_easy_part2.mp4")
        for bad in ("../x.mp4", "quiz_easy.mp4/../../y", "quiz_easy.mov", "QUIZ_EASY.mp4", "quiz_easy_part11.mp4", ""):
            with self.assertRaises(ValueError):
                quiz_export_job.export_storage_path("abc", 1, bad)


class RestoreAudioTests(unittest.TestCase):
    def setUp(self):
        self.data = {**compile_quiz(script()), "voice_id": "voice-1"}
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, True))
        patcher = mock.patch.object(quiz_export_job.quiz_shorts, "ensure_padded_audio")
        self.padded = patcher.start()
        self.addCleanup(patcher.stop)
        duration = mock.patch.object(quiz_export_job.tts, "get_duration_seconds", return_value=4.0)
        duration.start()
        self.addCleanup(duration.stop)

    @staticmethod
    def _write(audio, words=None):
        audio.write_bytes(b"mp3")
        if words is not None:
            words.write_text("[]")
        return True

    def run_restore(self, full=lambda k, a, w: True, audio_only=lambda k, a: False, synth=None, env=None):
        synth = synth or mock.Mock(side_effect=lambda text, voice, out, key: (Path(out).write_bytes(b"mp3"), [{"text": "x", "start": 0, "end": 1}])[1])
        with mock.patch.object(quiz_export_job.asset_store, "restore_voice", side_effect=lambda k, a, w: self._write(a, w) if full(k, a, w) else False), \
                mock.patch.object(quiz_export_job.asset_store, "restore_voice_audio", side_effect=lambda k, a: self._write(a) if audio_only(k, a) else False), \
                mock.patch.object(quiz_export_job.asset_store, "save_voice") as save, \
                mock.patch.object(quiz_export_job.tts, "synthesize_with_timestamps", synth), \
                mock.patch.dict(quiz_export_job.os.environ, env if env is not None else {"ELEVENLABS_API_KEY": "k"}):
            return quiz_export_job.restore_audio(self.data, self.tmp), synth, save

    def test_complete_cache_synthesizes_nothing(self):
        stats, synth, save = self.run_restore()
        self.assertEqual(stats, {"restored": 107, "approximate_words": 0, "synthesized": 0})
        synth.assert_not_called()
        self.assertEqual(self.padded.call_count, 50)  # one reflection window per question block

    def test_missing_voice_id_is_refused(self):
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_export_job.restore_audio({**self.data, "voice_id": None}, self.tmp)

    def test_audio_without_timings_gets_even_timings_and_costs_nothing(self):
        stats, synth, _ = self.run_restore(full=lambda k, a, w: False, audio_only=lambda k, a: True)
        self.assertEqual(stats["approximate_words"], 107)
        synth.assert_not_called()
        words = json.loads((self.tmp / "audio" / "block-02.words.json").read_text())
        self.assertEqual(len(words), len(self.data["blocks"][1]["text"].split()))
        self.assertAlmostEqual(words[-1]["end"], 4.0, delta=0.05)

    def test_only_the_missing_blocks_are_synthesized_and_cached(self):
        calls = {"n": 0}
        def full(key, audio, words):
            calls["n"] += 1
            return calls["n"] > 7  # the first seven blocks have no cached voice (the real case: 100 of 107 cached)
        stats, synth, save = self.run_restore(full=full)
        self.assertEqual(stats["synthesized"], 7)
        self.assertEqual(stats["restored"], 100)
        self.assertEqual(synth.call_count, 7)
        self.assertEqual(save.call_count, 7)  # cached, so the next export reuses the very same voice

    def test_too_many_missing_voices_fail_instead_of_spending(self):
        with self.assertRaisesRegex(quiz_shorts.ExportError, "régénère"):
            self.run_restore(full=lambda k, a, w: False)  # all 107 missing: over the bound
        synth = mock.Mock()
        with self.assertRaises(quiz_shorts.ExportError):
            self.run_restore(full=lambda k, a, w: False, synth=synth)
        synth.assert_not_called()

    def test_missing_voice_without_a_provider_key_is_an_actionable_error(self):
        seen = []
        with self.assertRaisesRegex(quiz_shorts.ExportError, "indisponible"):
            self.run_restore(full=lambda k, a, w: (seen.append(k), len(seen) > 3)[1], env={})


class ProcessTests(unittest.TestCase):
    def test_stale_version_is_refused_before_any_work(self):
        client = Client({"content_items": {"script": {}, "current_version_id": "new"}})
        with self.assertRaisesRegex(quiz_shorts.ExportError, "régénérée"):
            quiz_export_job.process(client, {"content_item_id": "i", "chapter": 1, "source_version_id": "old"})

    def test_success_uploads_whitelisted_paths_and_cleans_up(self):
        data = compile_quiz(script())
        client = Client({"content_items": {"script": data, "current_version_id": "v"},
                         "content_versions": {"version_number": 4}})
        created = []
        real_mkdtemp = tempfile.mkdtemp

        def fake_export(d, work, out, chapters):
            (Path(out)).mkdir(parents=True, exist_ok=True)
            (Path(out) / "quiz_medium.mp4").write_bytes(b"x")
            return {"items": [{"file": "quiz_medium.mp4", "status": "ready", "part": 1, "parts": 1, "first_question": 11,
                               "last_question": 20, "duration": 120.0, "width": 1080, "height": 1920, "bytes": 1,
                               "short_eligible": True, "error": None}]}
        with mock.patch.object(quiz_export_job, "restore_audio"), \
                mock.patch.object(quiz_export_job.quiz_shorts, "export_chapters", side_effect=fake_export), \
                mock.patch.object(quiz_export_job.asset_store, "configure"), mock.patch.object(quiz_export_job.asset_store, "reset"), \
                mock.patch.object(quiz_export_job.storage, "_upload") as upload, \
                mock.patch.object(quiz_export_job.tempfile, "mkdtemp", side_effect=lambda **k: created.append(real_mkdtemp(**k)) or created[-1]):
            fields = quiz_export_job.process(client, {"content_item_id": "item-1", "chapter": 2, "source_version_id": "v"})
        self.assertEqual(upload.call_args.args[1], "item-1/shorts/v4/quiz_medium.mp4")
        self.assertEqual(fields["status"], "ready")
        self.assertEqual(fields["storage_paths"], {"quiz_medium.mp4": "item-1/shorts/v4/quiz_medium.mp4"})
        self.assertNotIn("storage_paths", fields["outputs"][0])
        self.assertFalse(Path(created[0]).exists())  # temp workspace removed

    def test_failed_render_raises_and_still_cleans_up(self):
        data = compile_quiz(script())
        client = Client({"content_items": {"script": data, "current_version_id": "v"}})
        created = []
        real_mkdtemp = tempfile.mkdtemp
        failing = {"items": [{"file": "quiz_easy.mp4", "status": "failed", "error": "Résolution inattendue"}]}
        with mock.patch.object(quiz_export_job, "restore_audio"), \
                mock.patch.object(quiz_export_job.quiz_shorts, "export_chapters", return_value=failing), \
                mock.patch.object(quiz_export_job.asset_store, "configure"), mock.patch.object(quiz_export_job.asset_store, "reset"), \
                mock.patch.object(quiz_export_job.storage, "_upload") as upload, \
                mock.patch.object(quiz_export_job.tempfile, "mkdtemp", side_effect=lambda **k: created.append(real_mkdtemp(**k)) or created[-1]):
            with self.assertRaisesRegex(quiz_shorts.ExportError, "Résolution"):
                quiz_export_job.process(client, {"content_item_id": "i", "chapter": 1, "source_version_id": "v"})
        upload.assert_not_called()
        self.assertFalse(Path(created[0]).exists())


class RepoTests(unittest.TestCase):
    def test_claim_returns_first_row_or_none(self):
        self.assertEqual(repo.claim_quiz_chapter_export(Client({"rpc:claim_quiz_chapter_export": [{"id": "x"}]}))["id"], "x")
        self.assertIsNone(repo.claim_quiz_chapter_export(Client({"rpc:claim_quiz_chapter_export": []})))

    def test_fail_truncates_error(self):
        client = Client({})
        repo.fail_quiz_chapter_export(client, "id", "e" * 900)
        update = next(c for c in client.log if c[1] == "update")
        self.assertEqual(update[2][0]["status"], "failed")
        self.assertEqual(len(update[2][0]["error"]), 500)


if __name__ == "__main__":
    unittest.main()
