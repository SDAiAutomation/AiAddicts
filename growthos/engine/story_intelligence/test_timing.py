"""Run: python -m unittest growthos.engine.story_intelligence.test_timing -v"""
import unittest
from copy import deepcopy
from growthos.engine.story_intelligence.timing import align_storyboard


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.story = {"target_duration_s": 10, "shots": [{"id": "s1", "duration_s": 5}, {"id": "s2", "duration_s": 5}]}

    def test_fits(self):
        result, report = align_storyboard(self.story, {"s1": 3, "s2": 4})
        self.assertTrue(report["fits_target"])
        self.assertEqual(result["shots"][-1]["end_s"], 10)

    def test_no_truncation(self):
        result, report = align_storyboard(self.story, {"s1": 7, "s2": 4})
        self.assertGreater(result["shots"][0]["duration_s"], 7)
        self.assertFalse(report["ready_for_render"])

    def test_does_not_mutate(self):
        before = deepcopy(self.story)
        align_storyboard(self.story, {"s1": 3, "s2": 4})
        self.assertEqual(self.story, before)

    def test_missing_audio_rejected(self):
        with self.assertRaises(ValueError):
            align_storyboard(self.story, {"s1": 3})

    def test_nonfinite_audio_rejected(self):
        with self.assertRaises(ValueError):
            align_storyboard(self.story, {"s1": float("nan"), "s2": 4})

    def test_duplicate_ids_rejected(self):
        self.story["shots"][1]["id"] = "s1"
        with self.assertRaises(ValueError):
            align_storyboard(self.story, {"s1": 3})


if __name__ == "__main__":
    unittest.main()
