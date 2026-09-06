import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import visuals


class TestBuildCharacterPrefix(unittest.TestCase):
    def test_empty_when_no_characters_and_no_style(self):
        self.assertEqual(visuals.build_character_prefix(None, None), "")
        self.assertEqual(visuals.build_character_prefix([], ""), "")

    def test_character_sentence_and_negative(self):
        prefix = visuals.build_character_prefix(
            [{
                "name": "Léo",
                "description": "un ourson brun, petit, avec un pull rouge",
                "negative": "jamais un enfant humain, toujours un ourson anthropomorphe",
            }],
            None,
        )
        self.assertIn("Léo est un ourson brun, petit, avec un pull rouge.", prefix)
        self.assertIn("Ne jamais le représenter autrement", prefix)
        self.assertIn("ourson anthropomorphe", prefix)

    def test_incomplete_entries_are_skipped(self):
        prefix = visuals.build_character_prefix(
            [
                {"name": "Léo"},                      # pas de description
                {"description": "un renard"},          # pas de nom
                "pas un dict",
                {"name": "Mia", "description": "une chouette grise"},
            ],
            None,
        )
        self.assertNotIn("Léo", prefix)
        self.assertIn("Mia est une chouette grise.", prefix)

    def test_known_visual_style_id_is_translated(self):
        prefix = visuals.build_character_prefix(None, "anime_3d")
        self.assertIn("Style graphique identique pour toute la vidéo", prefix)
        self.assertIn("animation", prefix)

    def test_freeform_visual_style_used_as_is(self):
        prefix = visuals.build_character_prefix(None, "aquarelle douce, album jeunesse")
        self.assertIn("aquarelle douce, album jeunesse", prefix)

    def test_flat_color_style_adds_nothing(self):
        self.assertEqual(visuals.build_character_prefix(None, "flat_color"), "")


class TestScenePrompt(unittest.TestCase):
    def test_prefix_leads_and_action_follows(self):
        prefix = visuals.build_character_prefix(
            [{"name": "Léo", "description": "un ourson brun"}], "minimal_slides"
        )
        prompt = visuals._scene_prompt(
            ["Léo se réveille dans sa chambre.", "Il descend prendre son petit déjeuner."],
            "histoires-enfants",
            prefix,
            "9:16",
        )
        self.assertTrue(prompt.startswith("Léo est un ourson brun."))
        self.assertIn("SANS AUCUN TEXTE", prompt)
        self.assertIn("format 9:16", prompt)
        self.assertLess(prompt.index("Léo est un ourson brun."), prompt.index("Scène :"))
        self.assertIn("Scène : Léo se réveille dans sa chambre. Il descend", prompt)

    def test_falls_back_to_generic_style_without_prefix(self):
        prompt = visuals._scene_prompt(["Une réunion d'équipe."], "coach-business", "", "9:16")
        self.assertIn("Photo réaliste", prompt)
        self.assertIn("SANS AUCUN TEXTE", prompt)


class TestGroupBlocks(unittest.TestCase):
    def test_groups_of_three(self):
        self.assertEqual(visuals._group_blocks(7, 3), [[0, 1, 2], [3, 4, 5], [6]])


if __name__ == "__main__":
    unittest.main()
