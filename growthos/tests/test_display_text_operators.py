"""Les opérateurs arithmétiques d'un texte affiché ne doivent jamais disparaître
ni changer de sens : « REVENU - EPARGNE = BUDGET » perdait son moins parce que
`strip_directions` retirait tout tiret en tête de chaîne."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw, ImageFont

from engine.motion_graphics import canvas, display_text

M = display_text.MINUS


class TestOperatorsSurvive(unittest.TestCase):
    def test_expressions_keep_their_operators(self):
        cases = {
            "2000 - 300 = 1700": f"2000 {M} 300 = 1700",
            "REVENU - EPARGNE = BUDGET": f"REVENU {M} EPARGNE = BUDGET",
            "INCOME - SAVINGS = BUDGET": f"INCOME {M} SAVINGS = BUDGET",
            "x - 3 = 7": f"x {M} 3 = 7",
            "-5 + 2 = -3": f"{M}5 + 2 = {M}3",
            "12 ÷ 3 = 4": "12 ÷ 3 = 4",
            "2 × 5 = 10": "2 × 5 = 10",
            "3 + 4 = 7": "3 + 4 = 7",
            "x ≠ 1": "x ≠ 1",
            "x ≤ 3": "x ≤ 3",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(display_text.strip_directions(raw), expected)

    def test_unicode_minus_is_left_untouched(self):
        self.assertEqual(display_text.strip_directions(f"{M} EPARGNE", operators=True), f"{M} EPARGNE")
        self.assertEqual(display_text.strip_directions(f"REVENU {M} EPARGNE = BUDGET"), f"REVENU {M} EPARGNE = BUDGET")

    def test_negative_values_keep_their_sign(self):
        self.assertEqual(display_text.strip_directions("-$500"), f"{M}$500")
        self.assertEqual(display_text.strip_directions("-12%"), f"{M}12%")

    def test_a_formula_term_starting_with_minus_stays_a_subtraction(self):
        scene = display_text.viewer_scene({"sceneType": "formula", "terms": ["REVENU", "- EPARGNE", "= BUDGET"]})
        self.assertEqual(scene["terms"], ["REVENU", f"{M} EPARGNE", "= BUDGET"])

    def test_formula_terms_in_english_and_french(self):
        for terms, expected in (
            (["$3,000", "- $600", "= $2,400"], ["$3,000", f"{M} $600", "= $2,400"]),
            (["Salaire", "- Loyer", "= Reste"], ["Salaire", f"{M} Loyer", "= Reste"]),
        ):
            with self.subTest(terms=terms):
                self.assertEqual(display_text.viewer_scene({"sceneType": "formula", "terms": terms})["terms"], expected)


class TestOrdinaryTextIsUnchanged(unittest.TestCase):
    def test_hyphens_inside_words_and_ranges(self):
        for text in ("Aurais-tu ouvert la boite", "well-known idea", "2000-3000", "peut-etre"):
            with self.subTest(text=text):
                self.assertEqual(display_text.strip_directions(text), text)

    def test_prose_dash_between_words_is_not_a_minus(self):
        self.assertEqual(display_text.strip_directions("Wants - needs"), "Wants - needs")

    def test_list_bullet_hyphen_is_still_dropped_outside_formulas(self):
        self.assertEqual(display_text.strip_directions("- Save first"), "Save first")
        scene = display_text.viewer_scene({"sceneType": "checklist", "items": ["- Save first", "- Spend the rest"]})
        self.assertEqual(scene["items"], ["Save first", "Spend the rest"])

    def test_dangling_trailing_hyphen_is_dropped(self):
        self.assertEqual(display_text.strip_directions("Epargne -"), "Epargne")

    def test_equation_steps_are_not_rewritten(self):
        scene = display_text.viewer_scene({"sceneType": "equation_steps", "steps": [{"equation": "x - 3 = 7"}, {"equation": "x = 10"}]})
        self.assertEqual(scene["steps"][0]["equation"], "x - 3 = 7")

    def test_direction_stripping_still_works(self):
        self.assertEqual(display_text.strip_directions("Save first. Animation: icons pop in."), "Save first.")


class TestGlyphSupport(unittest.TestCase):
    SYMBOLS = f"{M}×÷+=≠≤≥≈±"

    def _ink(self, font, char):
        image = Image.new("L", (120, 120), 0)
        ImageDraw.Draw(image).text((10, 10), char, font=font, fill=255)
        return image.tobytes()

    def test_bundled_fonts_draw_every_operator(self):
        fonts = sorted(Path(canvas.__file__).resolve().parents[2].joinpath("assets", "fonts").rglob("*.ttf"))
        self.assertTrue(fonts)
        for path in fonts:
            font = ImageFont.truetype(str(path), 60)
            missing_glyph = self._ink(font, "￿")
            for char in self.SYMBOLS:
                with self.subTest(font=path.name, char=char):
                    self.assertNotEqual(self._ink(font, char), missing_glyph)


if __name__ == "__main__":
    unittest.main()
