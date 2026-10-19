"""Police de marque (Poppins) dans la mise en scène Motion : mêmes tailles visuelles qu'Arial, rien ne déborde."""
import json
import re
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from PIL import ImageFont

from engine import quiz_motion
from engine.captions import _quiz_events, write_ass
from engine.quiz import compile_quiz

RESOLUTIONS = ((720, 1280), (1080, 1920), (1080, 1080), (1920, 1080))
_FS = re.compile(r"\\fs(\d+)")
_POS = re.compile(r"\\(?:pos\((-?\d+),(-?\d+)\)|move\((-?\d+),(-?\d+),(-?\d+),(-?\d+))")
_READABLE = (",QuizQuestion,", ",QuizChoice,", ",QuizCorrect,")


def _scene(question: str, choices: list[str], phase: str = "question"):
    root = Path(__file__).resolve().parents[1]
    script = json.loads((root / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"]["presentation"] = "motion"
    item = script["quiz"]["questions"][0]
    item["question"], item["choices"], item["correct_choice"] = question, choices, 1
    block = [b for b in compile_quiz(script)["blocks"] if b["quiz_phase"] == phase][0]
    return {**block, "quiz_visual_available": False}


class BrandFontTests(unittest.TestCase):
    def test_the_brand_font_ships_with_the_engine(self):
        self.assertTrue(quiz_motion.brand_font_available())
        self.assertIsNotNone(quiz_motion.font_profile("Poppins"))
        self.assertIsNone(quiz_motion.font_profile("Arial"))
        self.assertIsNone(quiz_motion.font_profile(None))

    def test_visual_size_matches_the_default_font(self):
        block = _scene("What is the chemical symbol for sodium?", ["Na", "So", "Sd", "Nm"])
        def biggest(font):
            return max(int(m) for e in _quiz_events([block], [7], 1920, 1080, font) if ",QuizQuestion," in e
                       for m in _FS.findall(e))
        ratio = biggest("Poppins") / biggest(None)
        self.assertAlmostEqual(ratio, quiz_motion.FONT_PROFILES["Poppins"]["size_k"], delta=0.05)

    def test_lines_are_separate_events_at_the_visual_line_pitch(self):
        block = _scene("Which law states that pressure is inversely proportional to volume at constant temperature?",
                       ["Avogadro's law", "Boyle's law", "Charles's law", "Dalton's law"])
        events = [e for e in _quiz_events([block], [7], 1080, 1920, "Poppins")
                  if ",QuizQuestion," in e and "\\move(" in e and len(e.rsplit("}", 1)[-1]) > 12]
        self.assertGreaterEqual(len(events), 2)
        ys = sorted({int(_POS.search(e).group(6)) for e in events})
        sizes = {int(_FS.search(e).group(1)) for e in events}
        self.assertEqual(len(sizes), 1)
        pitch = ys[1] - ys[0]
        visual = next(iter(sizes)) / quiz_motion.FONT_PROFILES["Poppins"]["size_k"]
        self.assertAlmostEqual(pitch, visual * quiz_motion.FONT_PROFILES["Poppins"]["pitch"], delta=3)

    def test_no_line_is_wider_than_the_content_area_for_long_texts(self):
        bold = quiz_motion.FONT_DIR / "Poppins-Bold.ttf"
        long_question = "Which of the following chemical compounds is commonly used in disposable cold packs because dissolving it absorbs heat?"
        long_answers = [f"A deliberately long answer number {i} that goes on and on" for i in range(4)]
        for width, height in RESOLUTIONS:
            for phase in ("question", "reveal"):
                block = _scene(long_question, long_answers, phase)
                for event in _quiz_events([block], [7], width, height, "Poppins"):
                    if not any(style in event for style in _READABLE):
                        continue
                    text = event.rsplit("}", 1)[-1]
                    if len(text) < 6 or text.startswith("m "):
                        continue
                    fs = int(_FS.search(event).group(1))
                    # libass : la taille `\\fs` est la hauteur de cellule (ascendante + descendante = 1,4 em).
                    measured = ImageFont.truetype(str(bold), max(1, round(fs / 1.4))).getlength(text)
                    self.assertLessEqual(measured, width * 0.86, (width, height, phase, fs, text))

    def test_write_ass_uses_the_font_and_scales_the_captions(self):
        block = _scene("Quelle planète ?", ["Vénus", "Mercure", "Mars", "La Terre"], "reveal")
        with TemporaryDirectory() as folder:
            with_font = write_ass([], str(Path(folder) / "font-test.ass"), "bold_stroke", "1920x1080", font="Poppins", blocks=[block], block_durations=[3])
            default = write_ass([], str(Path(folder) / "font-test-default.ass"), "bold_stroke", "1920x1080", blocks=[block], block_durations=[3])
            self.assertIn("Style: QuizQuestion,Poppins,", Path(with_font).read_text(encoding="utf-8"))
            self.assertIn("Style: QuizQuestion,Arial,", Path(default).read_text(encoding="utf-8"))
            style = lambda path: next(l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("Style: Default,"))
            self.assertGreater(int(style(with_font).split(",")[2]), int(style(default).split(",")[2]) * 1.3)

    def test_classic_scenes_and_default_font_events_are_unchanged(self):
        block = _scene("Quelle planète ?", ["Vénus", "Mercure", "Mars", "La Terre"])
        self.assertEqual(_quiz_events([block], [7], 1080, 1920), _quiz_events([block], [7], 1080, 1920, None))


if __name__ == "__main__":
    unittest.main()
