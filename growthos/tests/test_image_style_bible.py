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


if __name__ == "__main__":
    unittest.main()
