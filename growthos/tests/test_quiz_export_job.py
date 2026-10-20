"""Job worker des exports de chapitre : cache audio, isolation, échecs sans effet sur le master."""
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

    def test_cache_miss_fails_without_synthesizing(self):
        with mock.patch.object(quiz_export_job.asset_store, "restore_voice", return_value=False), \
                mock.patch.object(quiz_export_job.tts, "synthesize_with_timestamps") as synth:
            with self.assertRaisesRegex(quiz_shorts.ExportError, "cache"):
                quiz_export_job.restore_audio(self.data, self.tmp)
            synth.assert_not_called()

    def test_missing_voice_id_is_refused(self):
        with self.assertRaises(quiz_shorts.ExportError):
            quiz_export_job.restore_audio({**self.data, "voice_id": None}, self.tmp)

    def test_cached_audio_is_restored_and_padded_blocks_rebuilt(self):
        def restore(key, audio, words):
            audio.write_bytes(b"mp3")
            words.write_text("[]")
            return True
        keys = []
        with mock.patch.object(quiz_export_job.asset_store, "restore_voice", side_effect=lambda k, a, w: (keys.append(k), restore(k, a, w))[1]), \
                mock.patch.object(quiz_shorts, "ensure_padded_audio") as padded:
            quiz_export_job.restore_audio(self.data, self.tmp)
        self.assertEqual(len(keys), len(self.data["blocks"]))
        self.assertEqual(len(set(keys)), len({b["text"] for b in self.data["blocks"]}))  # key follows the text
        self.assertEqual(padded.call_count, 50)  # one reflection window per question block


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
