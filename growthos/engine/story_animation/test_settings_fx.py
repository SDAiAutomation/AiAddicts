"""Procedural settings (a growing queue, rain, a shop at night): drawn by the scene over pictures the pack already has."""
import json
import unittest
from pathlib import Path

from growthos.engine.story_animation import contract, packs, pipeline, shotplan

FX = Path(__file__).parent / "fixtures"
SCENE = (Path(__file__).parent / "godot" / "rig_v1" / "scene.gd").read_text(encoding="utf-8")
NEW = {"street_queue": "bg_street", "street_rain": "bg_street", "clock_shop_closed": "bg_shop"}


def story(name):
    return json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))["story"]


class ProceduralSettings(unittest.TestCase):
    def test_the_catalog_is_the_sorted_list_of_the_plan_backgrounds(self):
        self.assertEqual(pipeline.RIG_V1_CATALOG["settings"], sorted(shotplan.BACKGROUNDS))
        self.assertTrue(set(NEW) <= set(pipeline.RIG_V1_CATALOG["settings"]))

    def test_the_new_settings_reuse_pictures_the_pack_already_holds(self):
        for setting, picture in NEW.items():
            self.assertEqual(shotplan.BACKGROUNDS[setting], picture)
            self.assertIn(picture, packs.REQUIRED_SPRITES)

    def test_the_scene_draws_each_procedural_setting(self):
        for fragment in ('"street_queue"', '"street_rain"', '"clock_shop_closed"', "func draw_queue(", "func draw_rain(", "func draw_night_shop(",
                         "draw_setting_back(cam, t, sh)", "draw_setting_front(cam, t, sh)"):
            self.assertIn(fragment, SCENE)

    def test_the_queue_is_bounded_and_grows_with_the_story_time(self):
        self.assertIn("const QUEUE_MAX := 44", SCENE)
        self.assertIn("clampi(6 + int(t * 1.6), 6, QUEUE_MAX)", SCENE)

    def test_the_pilot_scenarios_use_them_and_stay_valid(self):
        queue, umbrella = story("story_v21_la_file"), story("story_v21_parapluie")
        for s in (queue, umbrella, story("story_v21_ville_sans_mots")):
            self.assertEqual(contract.validate_animation_story(s, pipeline.RIG_V1_CATALOG), [])
        self.assertIn("street_queue", {x["setting_id"] for x in queue["shots"]})
        self.assertTrue({"street_rain", "clock_shop_closed"} <= {x["setting_id"] for x in umbrella["shots"]})

    def test_an_unknown_setting_is_still_refused(self):
        s = story("story_v21_la_file")
        s["shots"][0]["setting_id"] = "street_flood"
        self.assertTrue(any("setting_id is not an allowed catalog id" in e for e in contract.validate_animation_story(s, pipeline.RIG_V1_CATALOG)))


if __name__ == "__main__":
    unittest.main()
