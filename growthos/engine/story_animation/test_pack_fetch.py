import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation import demo_rig_v2, packs, pack_fetch
from growthos.engine.story_animation.pack_fetch import PackError


class FakeBucket:
    """The private bucket: object path -> bytes. Only paths that exist can be downloaded."""

    def __init__(self, pack_dir: Path, pack_id: str):
        manifest = pack_fetch.build_manifest(pack_dir, pack_id)
        self.objects = {f"{pack_id}/manifest.json": json.dumps(manifest).encode("utf-8")}
        for name in manifest["files"]:
            self.objects[f"{pack_id}/{name}"] = (pack_dir / name).read_bytes()
        self.requested = []

    def download(self, path: str) -> bytes:
        self.requested.append(path)
        if path not in self.objects:
            raise KeyError(path)
        return self.objects[path]


class PackFetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        packs.write_placeholder_pack(self.source)
        self.bucket = FakeBucket(self.source, "proto_v1")
        self.dest = self.root / "installed"

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_installs_a_valid_pack(self):
        manifest = pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        self.assertEqual(manifest["pack_id"], "proto_v1")
        self.assertEqual(packs.validate_pack(self.dest), [])
        self.assertFalse((self.root / "installed.part").exists())

    def test_only_expected_object_paths_are_requested(self):
        pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        expected = {"proto_v1/manifest.json"} | {f"proto_v1/{n}.png" for n in packs.REQUIRED_SPRITES}
        self.assertEqual(set(self.bucket.requested), expected)

    def test_tampered_file_is_rejected_and_nothing_is_installed(self):
        self.bucket.objects["proto_v1/hat.png"] = self.bucket.objects["proto_v1/hat.png"][:-1] + b"X"
        with self.assertRaisesRegex(PackError, "does not match"):
            pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.root / "installed.part").exists())

    def test_same_size_different_content_is_rejected(self):
        data = self.bucket.objects["proto_v1/torso.png"]
        self.bucket.objects["proto_v1/torso.png"] = bytes(reversed(data))
        with self.assertRaises(PackError):
            pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)

    def test_failed_update_keeps_the_previous_pack(self):
        pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        before = (self.dest / "hat.png").read_bytes()
        self.bucket.objects["proto_v1/clock.png"] = b"broken"
        with self.assertRaises(PackError):
            pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        self.assertEqual((self.dest / "hat.png").read_bytes(), before)

    def test_missing_object_leaves_no_partial_directory(self):
        del self.bucket.objects["proto_v1/shoe_l.png"]
        with self.assertRaises(KeyError):
            pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.root / "installed.part").exists())

    def test_manifest_must_list_exactly_the_required_files(self):
        manifest = json.loads(self.bucket.objects["proto_v1/manifest.json"])
        extra = copy.deepcopy(manifest)
        extra["files"]["../../etc/passwd"] = extra["files"]["hat.png"]
        missing = copy.deepcopy(manifest)
        del missing["files"]["hat.png"]
        for bad in (extra, missing):
            with self.subTest(keys=len(bad["files"])), self.assertRaises(PackError):
                pack_fetch.parse_manifest(bad, "proto_v1")

    def test_manifest_fields_are_checked(self):
        good = json.loads(self.bucket.objects["proto_v1/manifest.json"])
        cases = {
            "other pack": {**good, "pack_id": "other"},
            "bool version": {**good, "version": True},
            "zero version": {**good, "version": 0},
            "extra key": {**good, "note": "x"},
            "not an object": [],
        }
        entry = good["files"]["hat.png"]
        for label, mutate in {"bad sha": {**entry, "sha256": "ZZ"}, "huge size": {**entry, "bytes": 10 ** 9}, "bool size": {**entry, "bytes": True},
                              "extra field": {**entry, "path": "/tmp/x"}}.items():
            files = dict(good["files"])
            files["hat.png"] = mutate
            cases[label] = {**good, "files": files}
        for label, bad in cases.items():
            with self.subTest(label), self.assertRaises(PackError):
                pack_fetch.parse_manifest(bad, "proto_v1")

    def test_invalid_manifest_json(self):
        self.bucket.objects["proto_v1/manifest.json"] = b"not json"
        with self.assertRaisesRegex(PackError, "JSON"):
            pack_fetch.fetch_pack(self.bucket.download, "proto_v1", self.dest)

    def test_pack_id_is_validated_before_any_download(self):
        for bad in ("../x", "A", "", "a/b", "x" * 60, None, 5):
            with self.subTest(bad=bad), self.assertRaises(PackError):
                pack_fetch.fetch_pack(self.bucket.download, bad, self.dest)
        self.assertEqual(self.bucket.requested, [])

    def test_build_manifest_refuses_an_invalid_pack(self):
        (self.source / "hat.png").unlink()
        with self.assertRaises(PackError):
            pack_fetch.build_manifest(self.source, "proto_v1")

    def test_manifest_hashes_match_the_files(self):
        manifest = json.loads(self.bucket.objects["proto_v1/manifest.json"])
        data = (self.source / "clock.png").read_bytes()
        self.assertEqual(manifest["files"]["clock.png"], {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})


class RigPackFetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _, pack = demo_rig_v2.create(self.root / "fixture", frames_per_shot=12)
        self.source = pack / "tavi_owl"
        self.dest = self.root / "job" / "tavi_owl"
        self.objects = {f"tavi_owl/{path.name}": path.read_bytes() for path in self.source.iterdir() if path.is_file()}
        self.requested = []

    def download(self, path):
        self.requested.append(path)
        return self.objects[path]

    def test_fetches_only_declared_private_objects_and_installs_immutably(self):
        rig = pack_fetch.fetch_rig_pack(self.download, "tavi_owl", self.dest)
        self.assertEqual(rig["character_id"], "tavi_owl")
        self.assertEqual(set(self.requested), set(self.objects))
        self.assertEqual(set(path.name for path in self.dest.iterdir()), {path.name for path in self.source.iterdir()})
        with self.assertRaisesRegex(PackError, "already exists"):
            pack_fetch.fetch_rig_pack(self.download, "tavi_owl", self.dest)

    def test_tamper_or_path_like_id_never_installs_a_pack(self):
        self.objects["tavi_owl/head.png"] += b"tampered"
        with self.assertRaisesRegex(PackError, "does not match"):
            pack_fetch.fetch_rig_pack(self.download, "tavi_owl", self.dest)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.dest.parent.glob("tavi_owl.part.*")), [])
        self.requested.clear()
        with self.assertRaises(PackError):
            pack_fetch.fetch_rig_pack(self.download, "../other", self.dest)
        self.assertEqual(self.requested, [])


if __name__ == "__main__":
    unittest.main()
