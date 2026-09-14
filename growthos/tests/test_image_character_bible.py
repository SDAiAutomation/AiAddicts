import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import image_character_bible


class TestBuildCharacterPrefix(unittest.TestCase):
    def test_empty_when_no_characters_and_no_style(self):
        self.assertEqual(image_character_bible.build_character_prefix(None, None), "")
        self.assertEqual(image_character_bible.build_character_prefix([], ""), "")

    def test_character_sentence_and_negative(self):
        prefix = image_character_bible.build_character_prefix(
            [{
                "name": "Léo",
                "description": "un ourson brun, petit, avec un pull rouge",
                "negative": "jamais un enfant humain, toujours un ourson anthropomorphe",
            }],
            None,
        )
        self.assertIn("Si Léo apparaît dans cette scène", prefix)
        self.assertIn("Léo est un ourson brun, petit, avec un pull rouge.", prefix)
        self.assertIn("Ne jamais représenter Léo autrement", prefix)
        self.assertIn("ourson anthropomorphe", prefix)
        self.assertIn("Si aucun de ces personnages n'apparaît dans cette scène", prefix)

    def test_incomplete_entries_are_skipped(self):
        prefix = image_character_bible.build_character_prefix(
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
        prefix = image_character_bible.build_character_prefix(None, "anime_3d")
        self.assertIn("Style graphique identique pour toute la vidéo", prefix)
        self.assertIn("animation", prefix)

    def test_freeform_visual_style_used_as_is(self):
        prefix = image_character_bible.build_character_prefix(None, "aquarelle douce, album jeunesse")
        self.assertIn("aquarelle douce, album jeunesse", prefix)

    def test_flat_color_style_adds_nothing(self):
        self.assertEqual(image_character_bible.build_character_prefix(None, "flat_color"), "")

    def test_already_resolved_consigne_text_is_idempotent(self):
        # Le site d'appel réel (visuals.fetch_block_images) passe une consigne
        # DÉJÀ résolue (pas un id brut) — doit repasser inchangée.
        prefix = image_character_bible.build_character_prefix(
            None, "photo cinématique réaliste, objectif 35mm"
        )
        self.assertIn("photo cinématique réaliste, objectif 35mm", prefix)


if __name__ == "__main__":
    unittest.main()
