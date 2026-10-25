import copy
import json
import re
import unittest
from pathlib import Path

from growthos.engine.story_animation import coherence, pipeline, shotplan, visual_props
from growthos.engine.story_animation.test_shotplan import story, tl_for

HERE = Path(__file__).parent
SCENE = (HERE / "godot" / "rig_v1" / "scene.gd").read_text(encoding="utf-8")


def fixture(name):
    return json.loads((HERE / "fixtures" / f"story_v21_{name}.json").read_text(encoding="utf-8"))["story"]


class VisualProps(unittest.TestCase):
    def test_words_match_whole_and_without_accents(self):
        self.assertEqual([o for o, _ in visual_props.mentions("La CLÉ de ma boutique, et le Comité.")], ["key", "stamp"])
        self.assertEqual(visual_props.mentions("Une clémence rare"), [])          # a word that merely starts like one is not a match

    def test_an_absent_object_is_not_shown(self):
        self.assertEqual(visual_props.mentions("Je n'ai pas de parapluie."), [])
        self.assertEqual([o for o, _ in visual_props.mentions("Prenez ce parapluie.")], ["umbrella"])

    def test_schedule_follows_the_word_inside_the_line(self):
        events = visual_props.schedule("Un petit mot puis le dictionnaire et une clé tout à la fin.", 10.0, 6.0)
        self.assertEqual([e["id"] for e in events], ["book", "key"])
        self.assertTrue(10.0 < events[0]["start"] < events[1]["start"] < 16.0)
        self.assertLessEqual(events[0]["end"], events[1]["start"])                # the next object replaces the previous one
        self.assertTrue(all(e["end"] <= 16.4 for e in events))

    def test_every_object_has_a_drawing_in_the_scene(self):
        for oid in visual_props.OBJECT_IDS:
            self.assertIn(f'"{oid}":', SCENE, oid)


class ShotPlanObjects(unittest.TestCase):
    def test_the_plan_carries_the_objects_of_each_line(self):
        s = story()
        s["shots"][1]["dialogue"] = "Voici le dictionnaire de la ville."
        plan = shotplan.build_shot_plan(s, tl_for(s), pipeline.rig_roles(s))
        self.assertEqual([o["id"] for o in plan[1]["objects"]], ["book"])
        self.assertEqual(plan[0]["objects"], [])


class Review(unittest.TestCase):
    def test_a_long_narration_with_nothing_to_look_at_is_flagged(self):
        s = fixture("ville_sans_mots")
        kinds = [(i["shot"], i["kind"]) for i in coherence.review(s)]
        self.assertIn((10, "narration_without_anchor"), kinds)
        s["shots"][10]["dialogue"] += " Le « dictionnaire » en est un exemple."
        self.assertNotIn((10, "narration_without_anchor"), [(i["shot"], i["kind"]) for i in coherence.review(s)])

    def test_a_named_object_the_scene_cannot_draw_is_reported(self):
        s = fixture("parapluie")
        self.assertIn("mentioned_not_drawn", [i["kind"] for i in coherence.review(s)])

    def test_the_same_composition_three_times_in_a_row_is_a_stall(self):
        s = copy.deepcopy(fixture("parapluie"))
        for k in (7, 8, 9):
            s["shots"][k]["setting_id"], s["shots"][k]["shot_type"] = "clock_shop", "medium"
        self.assertIn("same_composition", [i["kind"] for i in coherence.review(s)])

    def test_a_short_scene_with_acting_has_no_issue(self):
        s = story()
        self.assertEqual([i for i in coherence.review(s) if i["kind"] == "narration_without_anchor"], [])


if __name__ == "__main__":
    unittest.main()
