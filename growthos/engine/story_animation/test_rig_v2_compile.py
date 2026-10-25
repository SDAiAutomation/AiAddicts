"""Measured voice and subtitle timing through the existing planner to the generic rig."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation import demo_rig_v2, rig_v2, rig_v2_compile, timeline as timeline_lib
from growthos.engine.story_animation.renderer import RenderError

FIXTURE = Path(__file__).parent / "fixtures" / "prototype_timeline.json"


class MeasuredCompileTests(unittest.TestCase):
    def setUp(self):
        self.tl = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.roles = {"pip": "pip", "ros": "rosette"}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        _, self.pack = demo_rig_v2.create(Path(self.temp.name), frames_per_shot=12)

    def test_existing_measured_timeline_compiles_without_new_tts(self):
        out = rig_v2_compile.compile_measured(self.tl, self.tl["shots"], self.roles)
        rig_v2.validate_timeline(out, self.pack)
        self.assertEqual(out["total_frames"], math.ceil(self.tl["total"] * 24))
        self.assertEqual(out["shots"][0]["start_frame"], 0)
        self.assertEqual(out["shots"][-1]["end_frame"], out["total_frames"])
        self.assertEqual(out["subs"][0]["text"], self.tl["subs"][0]["text"])
        speaking_frame = round(self.tl["lines"][0]["start"] * 24) + 5
        first = out["shots"][0]
        rosette = next(a for a in first["actors"] if a["character_id"] == "rosette")
        self.assertEqual(rosette["mouth_track"][speaking_frame], timeline_lib.mouth_at(self.tl, "ros", speaking_frame))
        self.assertEqual(first["actors"][0]["action"], self.tl["shots"][0]["actors"][0]["gesture"])

    def test_empty_composition_is_preserved(self):
        plan = copy.deepcopy(self.tl["shots"])
        plan[0]["empty"] = True
        out = rig_v2_compile.compile_measured(self.tl, plan, self.roles)
        self.assertEqual(out["shots"][0]["actors"], [])
        rig_v2.validate_timeline(out, self.pack)

    def test_unmapped_actor_and_invalid_subtitle_are_refused(self):
        with self.assertRaises(RenderError):
            rig_v2_compile.compile_measured(self.tl, self.tl["shots"], {"pip": "pip"})
        broken = copy.deepcopy(self.tl)
        broken["subs"][0]["end"] = broken["subs"][0]["start"]
        with self.assertRaises(RenderError):
            rig_v2_compile.compile_measured(broken, broken["shots"], self.roles)


if __name__ == "__main__":
    unittest.main()
