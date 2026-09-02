import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.captions import build_cues, format_timestamp


class TestFormatTimestamp(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")

    def test_minutes_and_millis(self):
        self.assertEqual(format_timestamp(65.5), "00:01:05,500")

    def test_hours(self):
        self.assertEqual(format_timestamp(3661.25), "01:01:01,250")

    def test_negative_clamped_to_zero(self):
        self.assertEqual(format_timestamp(-2), "00:00:00,000")


class TestBuildCues(unittest.TestCase):
    def test_cues_are_sequential(self):
        cues = build_cues([("bloc un", 2.0), ("bloc deux", 3.0)], gap=0.1)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertAlmostEqual(cues[0]["end"], 1.9)
        self.assertEqual(cues[1]["start"], 2.0)
        self.assertAlmostEqual(cues[1]["end"], 4.9)

    def test_cue_text_preserved(self):
        cues = build_cues([("hello", 1.0)])
        self.assertEqual(cues[0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
