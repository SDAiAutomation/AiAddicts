import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import image_character_bible, image_prompt_builder, image_style_bible


class TestBuildScenePrompt(unittest.TestCase):
    def test_prefix_leads_and_action_follows(self):
        prefix = image_character_bible.build_character_prefix(
            [{"name": "Léo", "description": "un ourson brun"}], "minimal_slides"
        )
        prompt = image_prompt_builder.build_scene_prompt(
            ["Léo se réveille dans sa chambre.", "Il descend prendre son petit déjeuner."],
            "histoires-enfants",
            prefix,
            "9:16",
        )
        self.assertTrue(prompt.startswith("BRIEF VISUEL"))
        self.assertIn("SANS AUCUN TEXTE", prompt)
        self.assertIn("format 9:16", prompt)
        self.assertLess(prompt.index("Léo est un ourson brun."), prompt.index("MOMENT NARRATIF"))
        self.assertIn("MOMENT NARRATIF : Léo se réveille dans sa chambre. Il descend", prompt)

    def test_falls_back_to_generic_style_without_prefix(self):
        prompt = image_prompt_builder.build_scene_prompt(["Une réunion d'équipe."], "coach-business", "", "9:16")
        self.assertIn("Photo réaliste", prompt)
        self.assertIn("SANS AUCUN TEXTE", prompt)

    def test_without_style_bible_uses_clean_generic_brief(self):
        prompt = image_prompt_builder.build_scene_prompt(["Une scène."], None, "", "9:16")
        self.assertNotIn("logo, filigrane", prompt)
        self.assertNotIn("zone centrale sûre", prompt)

    def test_style_bible_adds_avoid_list_and_composition_rules(self):
        style_bible = image_style_bible.resolve_style_bible("cinematic_real")
        prompt = image_prompt_builder.build_scene_prompt(
            ["Un homme marche dans une rue déserte."], None, "", "9:16", style_bible
        )
        self.assertIn("zone centrale sûre", prompt)
        self.assertIn("logo, filigrane", prompt)
        self.assertIn("SANS AUCUN TEXTE", prompt)  # toujours présent, pas remplacé


if __name__ == "__main__":
    unittest.main()
