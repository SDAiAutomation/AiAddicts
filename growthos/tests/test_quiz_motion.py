import json
from copy import deepcopy
from pathlib import Path
import unittest

from engine.captions import _quiz_events
from engine.quiz import compile_quiz, normalize_quiz, validate_quiz


class QuizMotionTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads((Path(__file__).resolve().parents[1] / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))

    def test_old_scripts_keep_identical_classic_events(self):
        compiled = compile_quiz(self.script)
        self.assertEqual(normalize_quiz(self.script["quiz"])["presentation"], "classic")
        old_blocks = deepcopy(compiled["blocks"])
        for block in old_blocks:
            block.pop("quiz_presentation", None)
        durations = [7] * len(old_blocks)
        self.assertEqual(_quiz_events(old_blocks, durations, 720, 1280),
                         _quiz_events(compiled["blocks"], durations, 720, 1280))

    def test_mode_roundtrips_and_recompilation_overrides_stale_block_mode(self):
        self.script["quiz"]["presentation"] = "motion"
        compiled = compile_quiz(self.script)
        self.assertTrue(all(b["quiz_presentation"] == "motion" for b in compiled["blocks"]))
        self.assertEqual(compile_quiz(compiled), compiled)
        compiled["quiz"]["presentation"] = "classic"
        self.assertTrue(all(b["quiz_presentation"] == "classic" for b in compile_quiz(compiled)["blocks"]))
        self.assertNotIn("blocks", self.script)

    def test_unknown_mode_rejected(self):
        for value in ("unknown", None, [], {}, 1):
            self.script["quiz"]["presentation"] = value
            with self.assertRaisesRegex(ValueError, "presentation"):
                validate_quiz(self.script["quiz"])

    def test_mode_switch_invalidates_generation_cache(self):
        from engine.generation_cache import fingerprint, _GENERATION_MODULES
        classic = fingerprint(compile_quiz(self.script), "voice")
        self.script["quiz"]["presentation"] = "motion"
        motion = compile_quiz(self.script)
        self.assertNotEqual(classic, fingerprint(motion, "voice"))
        self.assertIn("quiz_motion.py", _GENERATION_MODULES)
        self.assertEqual(motion["blocks"][0]["quiz_motion_version"], "quiz-motion:v2")

    def test_correct_answer_does_not_affect_question_frames(self):
        self.script["quiz"]["presentation"] = "motion"
        question = compile_quiz(self.script)["blocks"][1]
        for resolution in ((720, 1280), (1080, 1920), (1080, 1080), (1920, 1080)):
            original = _quiz_events([question], [7], *resolution)
            altered = _quiz_events([{**question, "quiz_correct_choice": 2}], [7], *resolution)
            self.assertEqual(original, altered)
            self.assertFalse(any(",QuizCorrect," in e or "✓" in e for e in original))

    def test_short_narration_has_no_choice_entrance_and_timer_is_bounded(self):
        self.script["quiz"]["presentation"] = "motion"
        question = compile_quiz(self.script)["blocks"][1]
        events = _quiz_events([question], [3.2], 720, 1280)
        self.assertFalse(any("\\move(" in e for e in events))
        for event in events:
            _, start, end, *_ = event.split(",")
            self.assertGreaterEqual(start, "0:00:00.00")
            self.assertLessEqual(end, "0:00:03.20")
        self.assertLess(len(events), 400)

    def test_reveal_uses_one_correct_row_and_escapes_user_text(self):
        self.script["quiz"]["presentation"] = "motion"
        self.script["quiz"]["questions"][0]["choices"][1] = r"Mercure {\pos(0,0)}"
        reveal = compile_quiz(self.script)["blocks"][2]
        events = _quiz_events([reveal], [3], 720, 1280)
        self.assertEqual(sum(",QuizCorrect," in e for e in events), 1)
        self.assertNotIn(r"{\pos(0,0)}", "\n".join(events))
        self.assertTrue(any("✓" in e for e in events))

    def test_four_visual_choices_stay_above_caption_band(self):
        import re
        self.script["quiz"]["presentation"] = "motion"
        self.script["quiz"]["questions"][0]["choices"].append("La Terre")
        reveal = {**compile_quiz(self.script)["blocks"][2], "quiz_visual_available": True}
        events = _quiz_events([reveal], [3], 720, 1280)
        rows = [e for e in events if ",QuizChoice," in e or ",QuizCorrect," in e]
        self.assertEqual(len(rows), 4)
        for event in rows:
            y = int(re.search(r"\\pos\(\d+,(\d+)\)", event).group(1))
            self.assertLess(y + 1280 * .020, 1280 * .645)


if __name__ == "__main__":
    unittest.main()
