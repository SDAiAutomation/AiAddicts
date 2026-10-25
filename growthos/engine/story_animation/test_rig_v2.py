"""Crosses the Python manifest, asset and frame-plan boundaries without a paid provider."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation import demo_rig_v2, rig_v2
from growthos.engine.story_animation.renderer import RenderError


class GenericRigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file, self.pack = demo_rig_v2.create(self.root, frames_per_shot=12)
        self.timeline = json.loads(self.file.read_text(encoding="utf-8"))

    def test_three_distinct_anatomies_need_no_character_branch_in_renderer(self):
        rigs = rig_v2.validate_timeline(self.timeline, self.pack)
        self.assertEqual(set(rigs), {"pip", "rosette", "tavi_owl"})
        widths = [abs(r["anchors"]["wrist_r"][0] - r["anchors"]["wrist_l"][0]) for r in rigs.values()]
        self.assertEqual(widths, [320, 460, 500])
        scene = (rig_v2.PROJECT_DIR / "scene.gd").read_text(encoding="utf-8")
        for character_id in rigs:
            self.assertNotIn('"' + character_id + '"', scene)

    def test_unapproved_actor_and_tampered_asset_fail_before_godot(self):
        invalid = copy.deepcopy(self.timeline)
        invalid["shots"][0]["actors"][0]["character_id"] = "../../other"
        with self.assertRaises(RenderError):
            rig_v2.validate_timeline(invalid, self.pack)
        path = self.pack / "tavi_owl" / "head.png"
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(RenderError, "hash differs"):
            rig_v2.validate_timeline(self.timeline, self.pack)

    def test_discontinuous_frames_or_unsupported_action_are_refused(self):
        for key, value in (("start_frame", 99), ("end_frame", 0)):
            invalid = copy.deepcopy(self.timeline)
            invalid["shots"][1][key] = value
            with self.subTest(key=key), self.assertRaises(RenderError):
                rig_v2.validate_timeline(invalid, self.pack)
        invalid = copy.deepcopy(self.timeline)
        invalid["shots"][1]["actors"][0]["action"] = "execute"
        with self.assertRaises(RenderError):
            rig_v2.validate_timeline(invalid, self.pack)
        invalid = copy.deepcopy(self.timeline)
        invalid["shots"][1]["actors"][0]["mouth_track"] = "c"
        with self.assertRaises(RenderError):
            rig_v2.validate_timeline(invalid, self.pack)


if __name__ == "__main__":
    unittest.main()
