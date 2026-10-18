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
        self.assertEqual(motion["blocks"][0]["quiz_motion_version"], "quiz-motion:v6")

    def test_correct_answer_does_not_affect_question_frames(self):
        self.script["quiz"]["presentation"] = "motion"
        question = compile_quiz(self.script)["blocks"][1]
        for resolution in ((720, 1280), (1080, 1920), (1080, 1080), (1920, 1080)):
            original = _quiz_events([question], [7], *resolution)
            altered = _quiz_events([{**question, "quiz_correct_choice": 2}], [7], *resolution)
            self.assertEqual(original, altered)
            self.assertFalse(any(",QuizCorrect," in e or "✓" in e for e in original))

    def test_landscape_text_is_sized_from_the_height_not_the_portrait_ratio(self):
        import re
        self.script["quiz"]["presentation"] = "motion"
        blocks = compile_quiz(self.script)["blocks"]
        for index, minimum in ((1, 40), (2, 28)):
            sizes = [int(m) for e in _quiz_events([blocks[index]], [7], 1920, 1080)
                     for m in re.findall(r"\\fs(\d+)", e)]
            self.assertGreaterEqual(max(sizes), 70)
            self.assertGreaterEqual(sorted(sizes)[len(sizes) // 2], minimum)
        # Portrait output is untouched by the landscape layout.
        portrait = [int(m) for e in _quiz_events([blocks[1]], [7], 1080, 1920) for m in re.findall(r"\\fs(\d+)", e)]
        self.assertGreaterEqual(max(portrait), 70)
        self.assertLessEqual(max(portrait), 76)

    def test_base_background_replaces_the_full_screen_rectangle_only_when_it_matches(self):
        from engine import quiz_motion
        self.script["quiz"]["presentation"] = "motion"
        compiled = compile_quiz(self.script)
        question = compiled["blocks"][1]

        def full_screen(events):
            return [e for e in events if "m 0 0 l 1080 0 1080 1920" in e]

        self.assertEqual(len(full_screen(_quiz_events([question], [7], 1080, 1920))), 1)
        same = {**question, "quiz_base_background": quiz_motion.stage_background(question.get("quiz_theme"))}
        self.assertEqual(full_screen(_quiz_events([same], [7], 1080, 1920)), [])
        other = {**question, "quiz_base_background": "#112233"}
        self.assertEqual(len(full_screen(_quiz_events([other], [7], 1080, 1920))), 1)

    def test_base_background_is_only_offered_for_motion_without_fades(self):
        from engine import quiz_motion
        motion = {**self.script, "quiz": {**self.script["quiz"], "presentation": "motion", "theme": "studio"}}
        self.assertEqual(quiz_motion.base_background_for(motion, 0.0), "0x080E1C")
        self.assertIsNone(quiz_motion.base_background_for(motion, 0.3))
        light = {**motion, "quiz": {**motion["quiz"], "theme": "minimal"}}
        self.assertEqual(quiz_motion.base_background_for(light, 0.0), "0xEEF2F6")
        classic = {**self.script, "quiz": {**self.script["quiz"], "presentation": "classic"}}
        self.assertIsNone(quiz_motion.base_background_for(classic, 0.0))
        self.assertIsNone(quiz_motion.base_background_for({"content_format": "standard"}, 0.0))

    def test_timer_ring_stays_light_for_long_quizzes(self):
        self.script["quiz"]["presentation"] = "motion"
        question = compile_quiz(self.script)["blocks"][1]
        events = _quiz_events([{**question, "hold_after_seconds": 5}], [12], 1920, 1080)
        rings = [e for e in events if e.count(" l ") > 40]
        self.assertLessEqual(len(rings), 5 * 12 + 1)

    def _long_blocks(self, presentation="motion", theme="studio"):
        questions = []
        for n in range(25):
            questions.append({"question": f"Which {('amber cobalt copper crimson emerald flint garnet indigo jade kelp lilac marble nickel onyx pearl quartz ruby sable topaz umber violet walnut xenon yellow zircon').split()[n]} substance dissolves near {n * 3 + 10} degrees?",
                              "choices": [f"Answer {n} first", f"Answer {n} second"], "correct_choice": 0, "fact": f"fact {n}"})
        script = {**self.script, "quiz": {**self.script["quiz"], "recipe": "long", "theme": theme,
                                          "presentation": presentation, "questions": questions}}
        return script, compile_quiz(script)["blocks"]

    def test_long_quizzes_change_background_by_part_and_short_ones_do_not(self):
        from engine import quiz_motion
        script, blocks = self._long_blocks()
        questions = [b for b in blocks if b["quiz_phase"] == "question"]
        parts = [quiz_motion.part_index(b) for b in questions]
        self.assertEqual(parts, sorted(parts))
        self.assertEqual(set(parts), {0, 1, 2, 3})
        self.assertEqual(parts[0], 0)
        self.assertEqual(parts[-1], 3)
        colours = [quiz_motion.base_background_for(script, 0.0, b) for b in questions]
        self.assertEqual(len(set(colours)), 4)
        self.assertEqual(quiz_motion.part_index([b for b in blocks if b["quiz_phase"] == "intro"][0]), 0)
        self.assertEqual(quiz_motion.part_index([b for b in blocks if b["quiz_phase"] == "outro"][0]), 3)
        # Un quiz de moins de 10 questions garde un seul fond.
        short = compile_quiz({**self.script, "quiz": {**self.script["quiz"], "presentation": "motion"}})["blocks"]
        self.assertEqual({quiz_motion.part_index(b) for b in short}, {0})
        # Pas de couleur pour le bloc de couverture, ni sans mode motion, ni avec fondu.
        self.assertIsNone(quiz_motion.base_background_for(script, 0.0, {"quiz_phase": "cover"}))
        self.assertIsNone(quiz_motion.base_background_for(script, 0.3, questions[0]))
        self.assertIsNone(quiz_motion.base_background_for({**script, "quiz": {**script["quiz"], "presentation": "classic"}}, 0.0, questions[0]))

    def test_scene_rectangle_follows_the_part_colour(self):
        from engine import quiz_motion
        script, blocks = self._long_blocks()
        late = [b for b in blocks if b["quiz_phase"] == "question"][-1]
        full = lambda events: [e for e in events if "m 0 0 l 1920 0 1920 1080" in e]
        matching = {**late, "quiz_base_background": quiz_motion.stage_background("studio", quiz_motion.part_index(late))}
        self.assertEqual(full(_quiz_events([matching], [12], 1920, 1080)), [])
        part_one = {**late, "quiz_base_background": quiz_motion.stage_background("studio", 0)}
        self.assertEqual(len(full(_quiz_events([part_one], [12], 1920, 1080))), 1)

    def test_answers_get_a_letter_chip_and_the_last_seconds_turn_urgent(self):
        from engine import quiz_motion
        script, blocks = self._long_blocks()
        question = [b for b in blocks if b["quiz_phase"] == "question"][3]
        events = _quiz_events([{**question, "hold_after_seconds": 5}], [12], 1920, 1080)
        chips = [e for e in events if ",QuizQuestion," in e and e.rsplit("}", 1)[-1] in {"A", "B"}]
        self.assertEqual(len(chips), 2)
        urgent = quiz_motion.URGENT_COLOUR.lstrip("#")
        urgent_bgr = "&H00" + urgent[4:6] + urgent[2:4] + urgent[0:2]
        urgent_events = [e for e in events if urgent_bgr.upper() in e.upper()]
        self.assertTrue(urgent_events)
        self.assertTrue(all(float(e.split(",")[1].split(":")[2]) >= 12 - 5 + 3 - 1e-6 for e in urgent_events if e.count(" l ") > 40))
        # Sur une scène claire, l'orange est assombri pour rester à 3:1 au moins.
        def contrast(first, second):
            def lum(colour):
                chans = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
                lin = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in chans]
                return .2126 * lin[0] + .7152 * lin[1] + .0722 * lin[2]
            high, low = sorted((lum(first), lum(second)), reverse=True)
            return (high + .05) / (low + .05)
        self.assertGreaterEqual(contrast(quiz_motion.URGENT_COLOUR_LIGHT, quiz_motion.stage_background("minimal")), 3.0)
        self.assertGreaterEqual(contrast(quiz_motion.URGENT_COLOUR, quiz_motion.stage_background("studio")), 3.0)
        light_script, light_blocks = self._long_blocks(theme="minimal")
        light_events = _quiz_events([{**[b for b in light_blocks if b["quiz_phase"] == "question"][3], "hold_after_seconds": 5}], [12], 1920, 1080)
        light_bgr = "&H00" + quiz_motion.URGENT_COLOUR_LIGHT[5:7].upper() + quiz_motion.URGENT_COLOUR_LIGHT[3:5].upper() + quiz_motion.URGENT_COLOUR_LIGHT[1:3].upper()
        self.assertTrue([e for e in light_events if light_bgr in e.upper()])
        # Un compte à rebours de moins de 3 secondes ne passe pas à l'orange.
        short_events = _quiz_events([{**question, "hold_after_seconds": 2}], [12], 1920, 1080)
        self.assertFalse([e for e in short_events if urgent_bgr.upper() in e.upper()])

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
        self.assertTrue(any("{check}" in e for e in events))  # coche dessinée, pas un glyphe

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
