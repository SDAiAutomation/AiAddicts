import json
import re
import unittest
from pathlib import Path

from engine.captions import _QUIZ_THEME_COLOURS, _quiz_events
from engine.quiz import QUIZ_THEMES, compile_quiz
from engine.quiz_motion import scene_events, stage_background


def _blocks(total):
    script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"]["theme"] = "vault"
    script["quiz"]["presentation"] = "motion"
    return [b for b in compile_quiz(script)["blocks"] if b["quiz_phase"] in {"question", "reveal"}]


def _texts(events):
    return [re.sub(r"\{[^}]*\}", "", line.split(",,", 1)[-1]) for line in events]


class VaultThemeTests(unittest.TestCase):
    def test_theme_is_known_everywhere(self):
        self.assertIn("vault", QUIZ_THEMES)
        self.assertIn("vault", _QUIZ_THEME_COLOURS)
        self.assertEqual(stage_background("vault", 0), "#0b0906")

    def test_portrait_header_has_plaque_slots_and_padlocks(self):
        question = _blocks(3)[0]
        events = _quiz_events([question], [7], 1080, 1920)
        joined = "\n".join(events)
        self.assertIn("THE VAULT", joined)
        self.assertIn("QUESTION 1 / 3", joined)

    def test_reveal_unlocks_the_current_slot_with_a_digit(self):
        blocks = _blocks(3)
        question, reveal = blocks[0], blocks[1]
        q = "\n".join(_quiz_events([question], [7], 1080, 1920))
        r = "\n".join(_quiz_events([reveal], [3], 1080, 1920))
        self.assertNotRegex(q, r"\}7\s*$")
        self.assertRegex(r, r"(?m)\}7$")
        self.assertNotIn("QUESTION 1 / 3", r)  # la plaque chevaucherait la question remontée

    def test_landscape_keeps_the_standard_header(self):
        events = _quiz_events([_blocks(3)[0]], [7], 1920, 1080)
        self.assertNotIn("THE VAULT", "\n".join(events))

    def test_many_questions_fall_back_without_slots(self):
        block = {**_blocks(3)[0], "quiz_question_total": 12, "quiz_question_number": 4}
        events = _quiz_events([block], [7], 1080, 1920)
        self.assertIn("THE VAULT", "\n".join(events))


if __name__ == "__main__":
    unittest.main()
