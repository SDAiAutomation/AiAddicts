import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import image_style_bible


class TestStyleConsigneFor(unittest.TestCase):
    def test_empty_for_none_or_empty(self):
        self.assertEqual(image_style_bible.style_consigne_for(None), "")
        self.assertEqual(image_style_bible.style_consigne_for(""), "")

    def test_known_id_translated(self):
        self.assertIn("anime", image_style_bible.style_consigne_for("anime"))

    def test_freeform_phrase_passthrough(self):
        self.assertEqual(image_style_bible.style_consigne_for("un style bien à moi"), "un style bien à moi")


class TestResolveStyleBible(unittest.TestCase):
    def test_visual_style_prompt_wins_over_visual_style_id(self):
        bible = image_style_bible.resolve_style_bible("anime", "phrase déjà résolue par le web")
        self.assertEqual(bible["consigne"], "phrase déjà résolue par le web")
        self.assertEqual(bible["visual_style_id"], "anime")

    def test_falls_back_to_catalog_when_no_prompt(self):
        bible = image_style_bible.resolve_style_bible("cinematic_real", None)
        self.assertIn("cinématique", bible["consigne"])

    def test_avoid_list_and_composition_rules_always_present(self):
        for style_id in ("cinematic_real", "anime", "flat_color", None):
            bible = image_style_bible.resolve_style_bible(style_id)
            self.assertTrue(bible["avoid"])
            self.assertIn("cadrage vertical", bible["composition_rules"].lower())

    def test_versions_present(self):
        bible = image_style_bible.resolve_style_bible(None)
        self.assertEqual(bible["version"], image_style_bible.STYLE_BIBLE_VERSION)
        self.assertEqual(bible["prompt_version"], image_style_bible.IMAGE_PROMPT_VERSION)

    def test_motion_profile_present_for_every_bible(self):
        for style_id in ("cinematic_real", "anime", "flat_color", "storybook", "comic_book", None, "unknown_id"):
            bible = image_style_bible.resolve_style_bible(style_id)
            self.assertIn("motion_profile", bible)
            self.assertTrue(bible["motion_profile"])

    def test_known_styles_map_to_expected_motion_profiles(self):
        self.assertEqual(image_style_bible.resolve_style_bible("cinematic_real")["motion_profile"], "cinematic")
        self.assertEqual(image_style_bible.resolve_style_bible("storybook")["motion_profile"], "gentle")
        self.assertEqual(image_style_bible.resolve_style_bible("comic_book")["motion_profile"], "comic")
        self.assertEqual(image_style_bible.resolve_style_bible("flat_color")["motion_profile"], "kinetic")
        self.assertEqual(image_style_bible.resolve_style_bible("stock_footage")["motion_profile"], "none")

    def test_legacy_style_ids_still_resolve_a_motion_profile(self):
        self.assertEqual(image_style_bible.resolve_style_bible("pixar_3d")["motion_profile"], "cinematic")
        self.assertEqual(image_style_bible.resolve_style_bible("gta_loading")["motion_profile"], "energetic")

    def test_unknown_style_defaults_transition_to_cut(self):
        for style_id in ("cinematic_real", "anime", "flat_color", None, "unknown_id"):
            self.assertEqual(image_style_bible.resolve_style_bible(style_id)["transition"], "cut")

    def test_storybook_opts_into_fade_transition(self):
        self.assertEqual(image_style_bible.resolve_style_bible("storybook")["transition"], "fade")

    def test_palette_contrast_texture_default_to_none(self):
        bible = image_style_bible.resolve_style_bible("cinematic_real")
        for field in ("palette", "contrast", "texture"):
            self.assertIn(field, bible)
        # cinematic_real définit contrast/texture mais pas palette :
        self.assertIsNone(bible["palette"])
        self.assertTrue(bible["contrast"])
        self.assertTrue(bible["texture"])

    def test_style_without_identity_has_no_palette_contrast_texture(self):
        bible = image_style_bible.resolve_style_bible("unknown_style_id")
        self.assertIsNone(bible["palette"])
        self.assertIsNone(bible["contrast"])
        self.assertIsNone(bible["texture"])

    def test_motion_profile_for_matches_resolve_style_bible(self):
        self.assertEqual(image_style_bible.motion_profile_for("comic_book"), "comic")
        self.assertIsNone(image_style_bible.motion_profile_for("not_a_real_style"))
        self.assertIsNone(image_style_bible.motion_profile_for(None))


if __name__ == "__main__":
    unittest.main()
