import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.subtitles import build_srt  # noqa: E402


class TestBuildSrt(unittest.TestCase):
    def test_single_block(self):
        srt = build_srt([("Bonjour le monde", 3.0)])
        self.assertIn("1\n00:00:00,000 --> 00:00:03,000\nBonjour le monde", srt)

    def test_sequential_timing(self):
        srt = build_srt([("Premier bloc", 2.5), ("Deuxième bloc", 1.5)])
        lines = srt.split("\n")
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[1], "00:00:00,000 --> 00:00:02,500")
        self.assertEqual(lines[2], "Premier bloc")
        self.assertEqual(lines[4], "2")
        self.assertEqual(lines[5], "00:00:02,500 --> 00:00:04,000")
        self.assertEqual(lines[6], "Deuxième bloc")

    def test_strips_whitespace(self):
        srt = build_srt([("  texte avec espaces  ", 1.0)])
        self.assertIn("texte avec espaces\n", srt)


if __name__ == "__main__":
    unittest.main()
