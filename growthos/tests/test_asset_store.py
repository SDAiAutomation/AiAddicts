"""Lot L1 — cache d'actifs : une correction ne repaie que ce qui a changé."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import asset_store, visuals


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, op, payload=None):
        self.db, self.op, self.payload, self.filters = db, op, payload, {}

    def select(self, _cols):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def in_(self, column, values):
        self.filters[column] = set(values)
        return self

    def upsert(self, row, on_conflict=None):
        self.op, self.payload = "upsert", row
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def execute(self):
        if self.op == "select":
            return _Result([r for r in self.db.rows if all(r.get(k) == v for k, v in self.filters.items())])
        if self.op == "upsert":
            row = {**self.payload, "id": f"id-{self.payload['kind']}-{self.payload['input_hash']}"}
            self.db.rows = [r for r in self.db.rows if r["id"] != row["id"]] + [row]
            return _Result([row])
        if self.op == "update":
            self.db.updated.append((self.payload, self.filters))
            return _Result([])
        raise AssertionError(self.op)


class _Bucket:
    def __init__(self, db):
        self.db = db

    def upload(self, path, local, file_options=None):
        self.db.objects[path] = Path(local).read_bytes()

    def download(self, path):
        return self.db.objects[path]


class FakeClient:
    """Mémoire de Supabase partagée entre deux « runs » successifs."""

    def __init__(self):
        self.rows, self.objects, self.updated = [], {}, []
        self.storage = self
        self.fail_table = False

    def from_(self, _bucket):
        return _Bucket(self)

    def table(self, _name):
        if self.fail_table:
            raise RuntimeError("relation content_assets does not exist")
        return _Query(self, "select")


def _blocks(second_visual="un chien qui court dans un champ"):
    return [
        {"role": "hook", "text": "un", "visual": "un chat noir assis sur un mur", "shotType": "close_up"},
        {"role": "point", "text": "deux", "visual": second_visual, "shotType": "wide"},
        {"role": "cta", "text": "trois", "visual": "un oiseau bleu sur une branche", "shotType": "medium"},
    ]


class TestAssetStoreInactive(unittest.TestCase):
    def setUp(self):
        asset_store.reset()

    def test_everything_is_a_noop_until_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "a.jpg"
            self.assertFalse(asset_store.enabled())
            self.assertFalse(asset_store.restore_image("k" * 32, dest))
            self.assertFalse(asset_store.restore_voice("k" * 32, dest, Path(tmp) / "w.json"))
            asset_store.save_image("k" * 32, dest)
            self.assertIsNone(asset_store.stats())

    def test_unavailable_manifest_leaves_the_cache_off_without_raising(self):
        client = FakeClient()
        client.fail_table = True
        asset_store.configure(client, "item-1")
        self.assertFalse(asset_store.enabled())

    def test_key_changes_with_any_input_and_is_stable_otherwise(self):
        base = asset_store.make_key(kind="voice", text="a", voice_id="v")
        self.assertEqual(base, asset_store.make_key(voice_id="v", text="a", kind="voice"))
        self.assertNotEqual(base, asset_store.make_key(kind="voice", text="b", voice_id="v"))
        self.assertNotEqual(base, asset_store.make_key(kind="voice", text="a", voice_id="w"))


class TestVoiceRoundTrip(unittest.TestCase):
    def tearDown(self):
        asset_store.reset()

    def test_voice_and_timing_are_restored_together(self):
        client = FakeClient()
        key = asset_store.make_key(kind="voice", text="bonjour", voice_id="v")
        with tempfile.TemporaryDirectory() as tmp:
            audio, words = Path(tmp) / "a.mp3", Path(tmp) / "a.words.json"
            audio.write_bytes(b"mp3")
            words.write_text("[]", encoding="utf-8")
            asset_store.configure(client, "item-1")
            asset_store.save_voice(key, audio, words, 0.01)

            asset_store.configure(client, "item-1")  # nouveau run, nouveau runner
            audio2, words2 = Path(tmp) / "b.mp3", Path(tmp) / "b.words.json"
            self.assertTrue(asset_store.restore_voice(key, audio2, words2))
            self.assertEqual(audio2.read_bytes(), b"mp3")
            self.assertEqual(asset_store.stats()["voice"], {"reused": 1, "generated": 0})

    def test_missing_timing_means_regenerate_not_half_restored(self):
        client = FakeClient()
        key = asset_store.make_key(kind="voice", text="bonjour", voice_id="v")
        with tempfile.TemporaryDirectory() as tmp:
            audio, words = Path(tmp) / "a.mp3", Path(tmp) / "a.words.json"
            audio.write_bytes(b"mp3")
            words.write_text("[]", encoding="utf-8")
            asset_store.configure(client, "item-1")
            asset_store.save_voice(key, audio, words)
            client.rows = [r for r in client.rows if r["kind"] != "voice_words"]

            asset_store.configure(client, "item-1")
            audio2, words2 = Path(tmp) / "b.mp3", Path(tmp) / "b.words.json"
            self.assertFalse(asset_store.restore_voice(key, audio2, words2))
            self.assertFalse(audio2.exists())


class TestSceneImagesAreOnlyRepaidWhenTheirInputsChange(unittest.TestCase):
    def tearDown(self):
        asset_store.reset()

    def _run(self, client, blocks):
        calls = []

        def fake_generate(prompt, out_path, *_args, **_kwargs):
            calls.append(prompt)
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"jpeg:" + prompt.encode("utf-8")[:20])
            return out_path

        asset_store.configure(client, "item-1")
        with tempfile.TemporaryDirectory() as tmp:  # runner éphémère : dossier neuf à chaque run
            env = {"OPENAI_API_KEY": "test-key", "IMAGE_QC_ENABLED": "false"}
            with patch.dict(os.environ, env), \
                 patch("engine.visuals.openai_images.generate_image", side_effect=fake_generate), \
                 patch("engine.visuals.openai_images.pop_last_usage", return_value=None), \
                 patch("engine.visuals.openai_images.pop_last_error", return_value=None):
                paths, _reports, _fallbacks, _treat = visuals.fetch_block_images(
                    blocks, None, "9:16", Path(tmp), None, visual_style="cinematic_real",
                )
            self.assertTrue(all(paths))
        return calls, asset_store.stats()["image"]

    def test_first_run_pays_for_every_scene(self):
        calls, image_stats = self._run(FakeClient(), _blocks())
        self.assertEqual(len(calls), 3)
        self.assertEqual(image_stats, {"reused": 0, "generated": 3})

    def test_identical_rerun_pays_for_nothing(self):
        client = FakeClient()
        self._run(client, _blocks())
        calls, image_stats = self._run(client, _blocks())
        self.assertEqual(calls, [])
        self.assertEqual(image_stats, {"reused": 3, "generated": 0})

    def test_changing_one_scene_regenerates_only_that_scene(self):
        client = FakeClient()
        self._run(client, _blocks())
        calls, image_stats = self._run(client, _blocks("un chien endormi sous la pluie"))
        self.assertEqual(len(calls), 1)
        self.assertIn("endormi", calls[0])
        self.assertEqual(image_stats, {"reused": 2, "generated": 1})


if __name__ == "__main__":
    unittest.main()
