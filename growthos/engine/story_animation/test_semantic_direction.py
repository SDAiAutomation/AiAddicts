"""Offline checks for conservative intent-based shot planning (run by the story-animation CI: this folder is what it discovers)."""
import copy
import json
import unittest

from growthos.engine.story_animation import pipeline, shotplan
from growthos.engine.story_animation.semantic_direction import direction
from growthos.engine.story_animation.shotplan import narrated_beats
from growthos.engine.story_animation.test_shotplan import FIXTURE, story, tl_for

CLOCK = [{"props": ["alarm_clock"]}]


class Direction(unittest.TestCase):
    def test_no_intent_keeps_legacy(self):
        self.assertIsNone(direction("", [], "narrator"))
        self.assertIsNone(direction("   ", CLOCK, "narrator"))

    def test_only_the_clock_the_scene_can_draw_makes_an_insert_and_only_over_the_narrator(self):
        self.assertEqual(direction("Look at the clock", CLOCK, "narrator")["shot_type"], "insert")
        self.assertIsNone(direction("Look at the clock", [{"props": []}], "narrator"))
        self.assertIsNone(direction("Open the book", CLOCK, "narrator"))        # a book is not the clock the scene would show
        self.assertNotEqual((direction("Look at the clock", CLOCK, "pip") or {}).get("shot_type"), "insert")   # never hide a speaking face

    def test_reveal_uses_supported_composition(self):
        self.assertEqual(direction("Discover the truth", [{"props": []}], "pip")["shot_type"], "close_up")
        self.assertEqual(direction("Reveal the secret", [{"props": []}], "narrator")["shot_type"], "medium")

    def test_narrated_beats_preserve_timing(self):
        entry = {
            "start": 0.0, "end": 12.0, "speaker": "narrator",
            "actors": [{"role": "pip", "gesture": "idle", "mood": "neutral", "props": []}],
            "shot_type": "wide", "camera": {"move": "static", "zoom_from": 1.0, "zoom_to": 1.0},
            "transition_in": "cut", "intent": "Discover the truth",
        }
        beats = narrated_beats(entry, 0)
        self.assertGreater(len(beats), 1)
        self.assertEqual(beats[0]["shot_type"], "medium")
        self.assertEqual(beats[0]["start"], 0.0)
        self.assertEqual(beats[-1]["end"], 12.0)
        self.assertFalse(any(beat.get("empty") for beat in beats))


class InPlan(unittest.TestCase):
    def plan_with(self, **changes):
        s = story()
        s["shots"][1].update(changes)
        return shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))[1], s

    def test_a_reframed_shot_takes_the_zoom_of_its_new_framing(self):
        base, s = self.plan_with()
        reframed, _ = self.plan_with(intent="Il découvre la vérité", shot_type="wide")
        self.assertEqual(reframed["shot_type"], "close_up")
        self.assertEqual((reframed["camera"]["zoom_from"], reframed["camera"]["zoom_to"]), (1.8, 2.2))
        self.assertEqual(reframed["intent"], "Il découvre la vérité")

    def test_an_explicit_author_camera_beats_the_intent(self):
        s = story()
        s["shots"][1]["camera"] = {"move": "static", "zoom_from": 1.1, "zoom_to": 1.1}
        s["shots"][1]["intent"] = "Il découvre la vérité"
        entry = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))[1]
        self.assertEqual(entry["shot_type"], s["shots"][1]["shot_type"])
        self.assertEqual(entry["camera"]["zoom_from"], 1.1)

    def test_a_story_without_intent_gets_exactly_the_old_plan(self):
        s = story()
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertTrue(all("intent" not in p for p in plan))


if __name__ == "__main__":
    unittest.main()
