import json
import re
import unittest
from pathlib import Path

from engine.captions import _QUIZ_THEME_COLOURS, _quiz_events
from engine.quiz import QUIZ_THEMES, compile_quiz
from engine.quiz_motion import SPLIT_LEFT, SPLIT_RIGHT, stage_background


def _blocks(choices):
    script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"]["theme"] = "split"
    script["quiz"]["presentation"] = "motion"
    question = script["quiz"]["questions"][0]
    question["choices"], question["correct_choice"] = choices, 0
    return [b for b in compile_quiz(script)["blocks"] if b["quiz_phase"] in {"question", "reveal"}]


def _luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))


class SplitThemeTests(unittest.TestCase):
    def test_theme_is_known_everywhere(self):
        self.assertIn("split", QUIZ_THEMES)
        self.assertIn("split", _QUIZ_THEME_COLOURS)
        self.assertEqual(stage_background("split", 0), "#0a1030")

    def test_white_text_is_readable_on_both_camps(self):
        for colour in (SPLIT_LEFT, SPLIT_RIGHT):
            self.assertGreaterEqual(1.05 / (_luminance(colour) + .05), 4.5, colour)

    def test_two_choices_in_portrait_use_the_split_scene(self):
        events = "\n".join(_quiz_events([_blocks(["Mercure", "Mars"])[0]], [7], 1080, 1920))
        self.assertIn("SPLIT DECISION", events)
        self.assertIn("Mercure", events)
        self.assertIn("Mars", events)

    def test_reveal_dims_the_wrong_camp_and_checks_the_right_one(self):
        blocks = _blocks(["Mercure", "Mars"])
        question = "\n".join(_quiz_events([blocks[0]], [7], 1080, 1920))
        reveal = "\n".join(_quiz_events([blocks[1]], [3], 1080, 1920))
        self.assertNotIn("\\alpha&H4C&", question)
        self.assertEqual(reveal.count("\\alpha&H4C&"), 1)
        self.assertEqual(reveal.count("{check}"), 1)

    def test_other_shapes_keep_the_standard_layout(self):
        four = "\n".join(_quiz_events([_blocks(["a", "b", "c", "d"])[0]], [7], 1080, 1920))
        two_landscape = "\n".join(_quiz_events([_blocks(["Mercure", "Mars"])[0]], [7], 1920, 1080))
        self.assertNotIn("SPLIT DECISION", four)
        self.assertNotIn("SPLIT DECISION", two_landscape)

    def test_check_path_draws_with_an_explicit_lineto(self):
        # Sans `l` après `m`, libass ne dessine pas la coche (défaut corrigé avec ce thème).
        reveal = "\n".join(_quiz_events([_blocks(["Mercure", "Mars"])[1]], [3], 1080, 1920))
        self.assertRegex(reveal, r"\}m \d+ \d+ l [\d ]+\{\\p0\}\{check\}")


if __name__ == "__main__":
    unittest.main()
