import copy
import json
import unittest
from pathlib import Path

from growthos.engine.story_animation import pipeline, shotplan, timeline
from growthos.engine.story_animation.test_timeline_lib import alignment, loud

FIXTURE = Path(__file__).parent / "fixtures"


def story():
    return json.loads((FIXTURE / "rig_v1_story.json").read_text(encoding="utf-8"))["story"]


def tl_for(s):
    lines = [{"who": pipeline.rig_roles(s)[x["speaker_id"]], "text": x["dialogue"], "duration_s": 2.0,
              "alignment": alignment("a" * 20, 0.1), "envelope": loud(48)} for x in s["shots"]]
    return timeline.build_timeline(lines)


class ShotPlanTests(unittest.TestCase):
    def test_one_shot_per_line_with_the_timeline_cuts(self):
        s = story()
        tl = tl_for(s)
        plan = shotplan.build_shot_plan(s, tl, pipeline.rig_roles(s))
        cuts = timeline.shot_cuts(tl)
        self.assertEqual([p["start"] for p in plan], cuts[:-1])
        self.assertEqual(plan[-1]["end"], tl["total"])
        self.assertEqual([p["index"] for p in plan], list(range(6)))

    def test_roles_replace_character_ids(self):
        s = story()
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertEqual({a["role"] for p in plan for a in p["actors"]}, {"pip", "ros"})
        self.assertEqual(plan[0]["speaker"], "ros")
        self.assertEqual(plan[0]["actors"][0]["gesture"], "accuse")
        self.assertEqual(plan[0]["actors"][1]["props"], ["alarm_clock"])

    def test_default_framing_by_shot_type(self):
        s = story()
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        by_type = {p["shot_type"]: p["camera"] for p in plan if p["speaker"] == "pip" or p["shot_type"] != "close_up"}
        self.assertEqual((by_type["wide"]["zoom_from"], by_type["wide"]["zoom_to"]), shotplan.WIDE)
        self.assertEqual((by_type["medium"]["zoom_from"], by_type["medium"]["zoom_to"]), shotplan.MEDIUM)
        self.assertEqual(plan[1]["camera"]["zoom_from"], shotplan.CLOSE_UP["pip"][0])   # Pip close-up
        self.assertEqual(plan[4]["camera"]["zoom_from"], shotplan.CLOSE_UP["ros"][0])   # Rosette close-up

    def test_explicit_camera_overrides_the_defaults(self):
        s = story()
        s["shots"][0]["camera"] = {"move": "pan_left", "zoom_from": 1.2, "zoom_to": 1.6}
        s["shots"][1]["camera"] = {"move": "static", "zoom_from": 2.5, "zoom_to": 3.9}
        s["shots"][2]["camera"] = {"move": "push_in"}
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertEqual(plan[0]["camera"], {"move": "pan_left", "zoom_from": 1.2, "zoom_to": 1.6})
        self.assertEqual(plan[1]["camera"], {"move": "static", "zoom_from": 2.5, "zoom_to": 2.5})  # static keeps one zoom
        self.assertEqual(plan[2]["camera"]["zoom_from"], shotplan.MEDIUM[0])

    def test_setting_maps_to_a_background_and_unknown_falls_back(self):
        s = story()
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertEqual(plan[0]["background"], "bg_shop")
        self.assertEqual(plan[5]["background"], "bg_street")
        s["shots"][0]["setting_id"] = "not_drawn_yet"
        self.assertEqual(shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))[0]["background"], "bg_shop")

    def test_transition_and_mood_defaults(self):
        s = story()
        s["shots"][1]["transition_in"] = "fade"
        del s["shots"][0]["actors"][0]["mood"]
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertEqual(plan[1]["transition_in"], "fade")
        self.assertEqual(plan[0]["transition_in"], "cut")
        self.assertEqual(plan[0]["actors"][0]["mood"], "neutral")

    def test_shots_and_lines_must_match(self):
        s = story()
        tl = tl_for(s)
        s["shots"].append(copy.deepcopy(s["shots"][0]))
        with self.assertRaises(ValueError):
            shotplan.build_shot_plan(s, tl, pipeline.rig_roles(s))

    def test_every_catalog_setting_has_a_background(self):
        self.assertEqual(set(pipeline.RIG_V1_CATALOG["settings"]), set(shotplan.BACKGROUNDS))


class FixtureConsistency(unittest.TestCase):
    def test_prototype_timeline_fixture_matches_the_plan_builder(self):
        tl = json.loads((FIXTURE / "prototype_timeline.json").read_text(encoding="utf-8"))
        s = story()
        self.assertEqual(tl["shots"], json.loads(json.dumps(shotplan.build_shot_plan(s, tl, pipeline.rig_roles(s)))))
        self.assertNotIn("rings", tl)


if __name__ == "__main__":
    unittest.main()
