import unittest

from engine.math_narration import for_voice
from engine.motion_graphics.math_steps import _find_phrase


class TestMathNarration(unittest.TestCase):
    def test_equation_and_prose(self):
        self.assertEqual(for_voice("5x + 2 = 2x + 14"), "5 iks plus 2 égale 2 iks plus 14")
        self.assertEqual(for_voice("Puis x = 4."), "Puis iks égale 4.")
        self.assertEqual(for_voice("exercice : maximum"), "exercice : maximum")

    def test_animation_anchor_accepts_spoken_iks(self):
        words = [(word, i, i + 0.2, False) for i, word in enumerate(("trois", "iks", "égale", "douze"))]
        self.assertEqual(_find_phrase(words, "trois x égale douze"), (0, 4))


if __name__ == "__main__":
    unittest.main()
