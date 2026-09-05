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
    def test_cues_offset_by_real_block_duration(self):
        # La durée réelle du bloc (2.0s) sert de décalage pour le bloc
        # suivant, pas la fin du dernier mot (0.8s) — sinon un blanc en fin
        # de bloc ferait dériver les cues suivantes par rapport à l'audio
        # concaténé (video.concat_audio ne met aucun blanc entre blocs).
        block1 = [
            {"text": "bloc", "start": 0.0, "end": 0.4},
            {"text": "un", "start": 0.4, "end": 0.8},
        ]
        block2 = [
            {"text": "bloc", "start": 0.0, "end": 0.5},
            {"text": "deux", "start": 0.5, "end": 1.0},
        ]
        cues = build_cues([(block1, 2.0), (block2, 3.0)], gap=0.1)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertAlmostEqual(cues[0]["end"], 0.9)
        self.assertEqual(cues[0]["text"], "bloc un")
        self.assertEqual(cues[1]["start"], 2.0)
        self.assertEqual(cues[1]["text"], "bloc deux")

    def test_words_grouped_by_three(self):
        words = [
            {"text": f"mot{i}", "start": i * 0.3, "end": i * 0.3 + 0.25}
            for i in range(7)
        ]
        cues = build_cues([(words, 2.5)])
        self.assertEqual(len(cues), 3)  # 7 mots -> groupes de 3, 3, 1
        self.assertEqual(cues[0]["text"], "mot0 mot1 mot2")
        self.assertEqual(cues[1]["text"], "mot3 mot4 mot5")
        self.assertEqual(cues[2]["text"], "mot6")

    def test_cue_end_never_exceeds_block_duration(self):
        words = [{"text": "fin", "start": 1.8, "end": 1.95}]
        cues = build_cues([(words, 2.0)], gap=0.15)
        self.assertLessEqual(cues[0]["end"], 2.0)


if __name__ == "__main__":
    unittest.main()
