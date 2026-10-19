"""Mise en page 16:9 en colonnes : question à gauche, réponses empilées à droite, stables à la révélation."""
import json
import re
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from engine import quiz_motion
from engine.captions import _quiz_events, write_ass
from engine.quiz import compile_quiz

_POS = re.compile(r"\\(?:pos\((-?\d+),(-?\d+)\)|move\((-?\d+),(-?\d+),(-?\d+),(-?\d+))")
_PATH = re.compile(r"m 0 0 l (\d+) 0 \d+ (\d+) 0 \d+")
_FS = re.compile(r"\\fs(\d+)")


def _end(event):
    pos = _POS.search(event)
    if not pos:
        return None
    return (int(pos.group(5)), int(pos.group(6))) if pos.group(5) else (int(pos.group(1)), int(pos.group(2)))


class ColumnsTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
        self.script["quiz"]["presentation"] = "motion"

    def _blocks(self, count=4):
        item = self.script["quiz"]["questions"][0]
        item["choices"] = ["Vénus", "Mercure", "Mars", "La Terre"][:count]
        item["correct_choice"] = 1
        blocks = compile_quiz(self.script)["blocks"]
        first = {}
        for block in blocks:  # la première question seulement (celle qu'on a modifiée)
            if block["quiz_phase"] in {"question", "reveal"}:
                first.setdefault(block["quiz_phase"], {**block, "quiz_visual_available": False})
        return first

    def test_only_wide_frames_use_columns(self):
        self.assertTrue(quiz_motion.uses_columns(1920, 1080))
        self.assertFalse(quiz_motion.uses_columns(1080, 1080))
        self.assertFalse(quiz_motion.uses_columns(1080, 1920))
        left, left_w, col_x, right = quiz_motion.column_layout(1920)
        self.assertLess(left + left_w, col_x)
        self.assertLess(col_x, right)
        self.assertGreater(col_x - (left + left_w), 40)  # gouttière

    def test_question_is_on_the_left_and_answers_on_the_right(self):
        _, left_w, col_x, _ = quiz_motion.column_layout(1920)
        left_edge = quiz_motion.column_layout(1920)[0]
        blocks = self._blocks()
        events = _quiz_events([blocks["question"]], [12], 1920, 1080, "Poppins")
        for event in events:
            end = _end(event)
            if end is None:
                continue
            text = event.rsplit("}", 1)[-1]
            if ",QuizChoice," in event:
                self.assertGreater(end[0], col_x, text)
            elif ",QuizQuestion," in event and len(text) > 12 and not text.startswith("m "):
                self.assertLess(end[0], left_edge + left_w, text)

    def test_answer_rows_do_not_move_between_question_and_reveal(self):
        for count in (2, 3, 4):
            blocks = self._blocks(count)
            _, _, col_x, right = quiz_motion.column_layout(1920)
            col_w = round(right - col_x)

            def rows(block):
                found = []
                for event in _quiz_events([block], [12], 1920, 1080):
                    path = _PATH.search(event)
                    if path and abs(int(path.group(1)) - col_w) <= 1 and int(path.group(2)) > 60 and ",QuizPanel," in event and "\\an7" in event:
                        found.append(_end(event))
                return sorted(set(found))
            question_rows, reveal_rows = rows(blocks["question"]), rows(blocks["reveal"])
            self.assertEqual(len(question_rows), count, count)
            self.assertEqual(question_rows, reveal_rows, count)
            self.assertTrue(all(0.2 * 1080 <= y <= 0.93 * 1080 for _, y in question_rows), count)

    def test_reveal_shows_the_answer_large_on_the_left_and_one_green_row(self):
        blocks = self._blocks()
        events = _quiz_events([blocks["reveal"]], [6], 1920, 1080, "Poppins")
        self.assertEqual(sum(",QuizCorrect," in e for e in events), 1)
        self.assertTrue(any("{check}" in e for e in events))
        _, left_w, col_x, _ = quiz_motion.column_layout(1920)
        hero = [e for e in events if e.rsplit("}", 1)[-1] == "Mercure" and ",QuizQuestion," in e]
        self.assertEqual(len(hero), 1)
        self.assertLess(_end(hero[0])[0], col_x)
        self.assertGreaterEqual(int(_FS.search(hero[0]).group(1)), 100)

    def test_captions_stay_in_the_left_column_only_for_wide_motion_quizzes(self):
        blocks = [self._blocks()["reveal"]]
        left, left_w, _, _ = quiz_motion.column_layout(1920)

        with TemporaryDirectory() as folder:
            def default_style(resolution, font=None, blocks=blocks):
                path = write_ass([], str(Path(folder) / "columns-test.ass"), "bold_stroke", resolution, font=font, blocks=blocks, block_durations=[3])
                return next(l for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("Style: Default,")).split(",")
            wide = default_style("1920x1080")
            self.assertEqual((int(wide[-4]), int(wide[-3])), (round(left), round(1920 - (left + left_w))))
            portrait = default_style("1080x1920")
            self.assertEqual((int(portrait[-4]), int(portrait[-3])), (60, 60))
            classic = default_style("1920x1080", blocks=[{**blocks[0], "quiz_presentation": "classic"}])
            self.assertEqual((int(classic[-4]), int(classic[-3])), (60, 60))

    def test_illustrated_questions_keep_the_centred_stack(self):
        block = {**self._blocks()["question"], "quiz_visual_available": True}
        events = _quiz_events([block], [12], 1920, 1080)
        question = [e for e in events if ",QuizQuestion," in e and "Quelle" in e]
        self.assertTrue(question)
        self.assertAlmostEqual(_end(question[0])[0], 960, delta=5)


if __name__ == "__main__":
    unittest.main()
