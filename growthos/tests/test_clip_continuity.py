"""Détecteur de creux d'encre des clips de maths (scripts/check_clip_continuity.py) : fonction pure."""
import runpy
import unittest
from pathlib import Path

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "check_clip_continuity.py"))
dips = MODULE["dips"]


class TestDips(unittest.TestCase):
    def test_a_blank_gap_between_two_states_is_reported(self):
        ink = [0.01] * 10 + [0.0] * 4 + [0.01] * 10
        found = dips(ink)
        self.assertEqual([index for index, _, _ in found], [10, 11, 12, 13])

    def test_a_crossfade_that_keeps_half_the_ink_is_not_a_dip(self):
        ink = [0.01] * 10 + [0.005] * 6 + [0.01] * 10
        self.assertEqual(dips(ink), [])

    def test_the_start_and_the_end_of_the_clip_are_not_judged(self):
        self.assertEqual(dips([0.0, 0.0, 0.01, 0.01, 0.0, 0.0]), [])

    def test_an_almost_empty_clip_is_ignored(self):
        self.assertEqual(dips([0.0005] * 5 + [0.0] * 3 + [0.0005] * 5), [])


if __name__ == "__main__":
    unittest.main()
