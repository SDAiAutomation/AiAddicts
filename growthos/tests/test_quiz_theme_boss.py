import json
import unittest
from pathlib import Path

from engine.captions import _QUIZ_THEME_COLOURS, _quiz_events
from engine.quiz import QUIZ_THEMES, compile_quiz
from engine.quiz_motion import stage_background


def _blocks():
    script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"]["theme"] = "boss"
    script["quiz"]["presentation"] = "motion"
    return [b for b in compile_quiz(script)["blocks"] if b["quiz_phase"] in {"question", "reveal"}]


class BossThemeTests(unittest.TestCase):
    def test_theme_is_known_everywhere(self):
        self.assertIn("boss", QUIZ_THEMES)
        self.assertIn("boss", _QUIZ_THEME_COLOURS)
        self.assertEqual(stage_background("boss", 0), "#150a33")

    def test_portrait_header_and_dark_ink_on_cream_cards(self):
        events = "\n".join(_quiz_events([_blocks()[0]], [7], 1080, 1920))
        self.assertIn("FINAL BOSS", events)
        self.assertIn("1 / 3", events)
        # Les réponses sont écrites en encre sombre (#1a0f3a) sur les cartes crème, pas en blanc.
        self.assertIn("\\1c&H003A0F1A}Vénus", events)

    def test_reveal_keeps_the_ladder_and_checks_the_current_level(self):
        blocks = _blocks()
        question = "\n".join(_quiz_events([blocks[0]], [7], 1080, 1920))
        reveal = "\n".join(_quiz_events([blocks[1]], [3], 1080, 1920))
        self.assertGreater(reveal.count("{check}"), question.count("{check}"))

    def test_landscape_only_changes_palette(self):
        self.assertNotIn("FINAL BOSS", "\n".join(_quiz_events([_blocks()[0]], [7], 1920, 1080)))


if __name__ == "__main__":
    unittest.main()
