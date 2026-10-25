"""Offline security and geometry checks for a prospective data-driven cutout rig."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation import packs, rig_manifest


class RigManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        self.pack.mkdir()
        for name, size in {"body": (180, 320), "head": (260, 180), "wing_l": (300, 100), "wing_r": (300, 100), "claw_l": (70, 80), "claw_r": (70, 80)}.items():
            packs._write_png(self.pack / f"{name}.png", *size, (115, 90, 60, 255))
        assets = {}
        for path in self.pack.glob("*.png"):
            w, h = packs.png_size(path)
            assets[path.stem] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "width": w, "height": h}
        self.rig = {
            "schema_version": 1, "character_id": "tavi_owl", "rig_type": "cutout_2d", "canvas": [700, 700],
            "anchors": {
                "hip": [350, 465], "neck": [350, 345], "shoulder_l": [290, 360], "shoulder_r": [410, 360],
                "hip_l": [320, 465], "hip_r": [380, 465], "wrist_l": [90, 390], "wrist_r": [610, 390],
                "ankle_l": [325, 580], "ankle_r": [375, 580],
            },
            "face": {"eye_l": [85, 70], "eye_r": [175, 70], "mouth": [130, 125]},
            "sprites": {"torso": "body", "head": "head", "hand_l": "wing_l", "hand_r": "wing_r", "foot_l": "claw_l", "foot_r": "claw_r"},
            "assets": assets, "expressions": ["neutral", "happy", "surprised"],
            "actions": ["idle", "walk", "talk", "point", "react"], "mouths": ["closed", "open", "round"],
        }

    def test_distinct_owl_anatomy_and_verified_assets_are_accepted(self):
        path = self.pack / "rig.json"
        path.write_text(json.dumps(self.rig), encoding="utf-8")
        self.assertEqual(rig_manifest.load_manifest(path, self.pack)["character_id"], "tavi_owl")
        self.assertEqual(self.rig["anchors"]["wrist_r"][0] - self.rig["anchors"]["wrist_l"][0], 520)

    def test_changed_image_is_refused_even_with_correct_dimensions(self):
        path = self.pack / "rig.json"
        path.write_text(json.dumps(self.rig), encoding="utf-8")
        packs._write_png(self.pack / "head.png", 260, 180, (220, 20, 20, 255))
        with self.assertRaisesRegex(rig_manifest.RigManifestError, "hash differs"):
            rig_manifest.load_manifest(path, self.pack)

    def test_manifest_outside_the_pack_is_refused(self):
        path = self.root / "rig.json"
        path.write_text(json.dumps(self.rig), encoding="utf-8")
        with self.assertRaisesRegex(rig_manifest.RigManifestError, "inside the approved pack"):
            rig_manifest.load_manifest(path, self.pack)

    def test_paths_scripts_and_unbounded_geometry_are_refused(self):
        for change in (
            lambda r: r["sprites"].update(head="../private"),
            lambda r: r.update(script="res://evil.gd"),
            lambda r: r["anchors"].update(hip=[float("nan"), 0]),
            lambda r: r["actions"].append("execute"),
            lambda r: r["expressions"].append({"code": "bad"}),
        ):
            rig = copy.deepcopy(self.rig)
            change(rig)
            with self.subTest(rig=rig), self.assertRaises(rig_manifest.RigManifestError):
                rig_manifest.validate_manifest(rig)


if __name__ == "__main__":
    unittest.main()
