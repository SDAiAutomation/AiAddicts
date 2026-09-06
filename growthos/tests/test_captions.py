import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.captions import (
    _ass_timestamp,
    build_cues,
    caption_style_or_default,
    format_timestamp,
    write_ass,
)


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

    def test_cue_carries_absolute_word_timings(self):
        block1 = [{"text": "a", "start": 0.0, "end": 0.4}, {"text": "b", "start": 0.4, "end": 0.8}]
        block2 = [{"text": "c", "start": 0.0, "end": 0.5}]
        cues = build_cues([(block1, 2.0), (block2, 3.0)])
        self.assertEqual([w["text"] for w in cues[0]["words"]], ["a", "b"])
        self.assertEqual(cues[1]["words"][0]["start"], 2.0)  # décalé du bloc 1


class TestAssTimestamp(unittest.TestCase):
    def test_format(self):
        self.assertEqual(_ass_timestamp(0), "0:00:00.00")
        self.assertEqual(_ass_timestamp(65.5), "0:01:05.50")
        self.assertEqual(_ass_timestamp(-3), "0:00:00.00")


class TestWriteAss(unittest.TestCase):
    def _cues(self):
        words = [
            {"text": "Leo", "start": 0.0, "end": 0.3},
            {"text": "se", "start": 0.3, "end": 0.5},
            {"text": "reveille", "start": 0.5, "end": 0.9},
        ]
        return build_cues([(words, 1.2)])

    def _write(self, style):
        path = Path(tempfile.mkdtemp()) / "captions.ass"
        return Path(write_ass(self._cues(), str(path), style, "1080x1920")).read_text(encoding="utf-8")

    def test_header_and_playres(self):
        ass = self._write("bold_stroke")
        self.assertIn("[V4+ Styles]", ass)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("Style: Default,", ass)
        self.assertIn("Dialogue: 0,0:00:00.00,", ass)

    def test_boxed_uses_opaque_box_border_style(self):
        # BorderStyle=3 (18e champ du Style) = boîte opaque
        line = next(l for l in self._write("boxed").splitlines() if l.startswith("Style: Default,"))
        fields = line[len("Style: "):].split(",")
        # Name,Font,Size,Prim,Sec,Out,Back,Bold,Ital,Under,Strike,ScaleX,ScaleY,Spacing,Angle,BorderStyle
        self.assertEqual(fields[15], "3")  # BorderStyle=3 -> boîte opaque

    def test_word_pop_emits_one_dialogue_per_word_with_highlight(self):
        ass = self._write("word_pop")
        dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        self.assertEqual(len(dialogues), 3)  # 3 mots -> 3 fenêtres
        self.assertIn("\\1c&H0000D7FF&", ass)  # couleur de surlignage
        self.assertIn("\\fscx118", ass)

    def test_unknown_style_falls_back(self):
        self.assertEqual(caption_style_or_default("nope"), "bold_stroke")
        self.assertEqual(caption_style_or_default("word_pop"), "word_pop")
        ass = self._write("nope")
        self.assertIn("Style: Default,", ass)

    def test_braces_in_text_are_neutralised(self):
        cues = [{"index": 1, "start": 0.0, "end": 1.0, "text": "un {evil} tag", "words": []}]
        path = Path(tempfile.mkdtemp()) / "c.ass"
        ass = Path(write_ass(cues, str(path), "sleek", "1080x1920")).read_text(encoding="utf-8")
        self.assertIn("un (evil) tag", ass)


if __name__ == "__main__":
    unittest.main()
