"""Plan structuré des scènes equation_steps : opérations, timeline sur les mots réels, validation à risque."""
import os
import unittest
from fractions import Fraction
from unittest import mock

from engine.motion_graphics import math_steps as ms
from engine.motion_graphics import math_validation as mv

# Mots RÉELS renvoyés par ElevenLabs (bloc de la vidéo de référence 3x + 6 = 18, voix de la niche mathématiques).
WORDS = [
    {"text": "On", "start": 0.0, "end": 0.2}, {"text": "veut", "start": 0.22, "end": 0.4},
    {"text": "isoler", "start": 0.43, "end": 0.9}, {"text": "x.", "start": 1.04, "end": 1.3},
    {"text": "On", "start": 1.49, "end": 1.6}, {"text": "retire", "start": 1.66, "end": 1.95},
    {"text": "six", "start": 2.02, "end": 2.2}, {"text": "des", "start": 2.23, "end": 2.33},
    {"text": "deux", "start": 2.36, "end": 2.45}, {"text": "côtés", "start": 2.48, "end": 2.85},
    {"text": ":", "start": 2.88, "end": 3.0}, {"text": "trois", "start": 3.04, "end": 3.6},
    {"text": "x", "start": 3.65, "end": 3.7}, {"text": "égale", "start": 3.75, "end": 3.95},
    {"text": "douze.", "start": 3.99, "end": 4.5}, {"text": "Puis", "start": 4.57, "end": 4.8},
    {"text": "on", "start": 4.85, "end": 4.95}, {"text": "divise", "start": 4.97, "end": 5.35},
    {"text": "les", "start": 5.39, "end": 5.48}, {"text": "deux", "start": 5.51, "end": 5.6},
    {"text": "côtés", "start": 5.64, "end": 5.9}, {"text": "par", "start": 5.92, "end": 6.02},
    {"text": "trois", "start": 6.06, "end": 6.3}, {"text": ":", "start": 6.35, "end": 6.4},
    {"text": "x", "start": 6.72, "end": 6.8}, {"text": "égale", "start": 6.85, "end": 7.1},
    {"text": "quatre.", "start": 7.14, "end": 7.6},
]
SCENE = {"sceneType": "equation_steps", "title": "Isoler x", "steps": [
    {"equation": "3x + 6 = 18", "explanation": "Objectif : isoler x", "spoken": "on veut isoler x"},
    {"equation": "3x = 12", "explanation": "−6 des deux côtés", "spoken": "on retire six"},
    {"equation": "x = 4", "explanation": "÷3 des deux côtés", "spoken": "puis on divise"},
]}


class TestOperations(unittest.TestCase):
    def test_subtraction_division_multiplication_and_x_terms(self):
        sub = mv.describe_operation("3x + 6 = 18", "3x = 12")
        self.assertEqual((sub["kind"], sub["tex"], sub["display"]), ("add", "-6", "−6"))
        div = mv.describe_operation("3x = 12", "x = 4")
        self.assertEqual((div["kind"], div["display"]), ("div", "÷3"))
        mul = mv.describe_operation("x/2 = 3", "x = 6")
        self.assertEqual((mul["kind"], mul["display"]), ("mul", "×2"))
        with_x = mv.describe_operation("2x - 3 = x + 5", "x - 3 = 5")
        self.assertEqual((with_x["kind"], with_x["withX"], with_x["display"]), ("add", True, "−x"))

    def test_plain_rewrite_and_unsupported_pairs_have_no_invented_operation(self):
        self.assertEqual(mv.describe_operation("2(x + 3) = 14", "2x + 6 = 14")["kind"], "rewrite")
        self.assertEqual(mv.describe_operation("x(x - 2) = 0", "x = 0 ou x = 2")["kind"], "unknown")

    def test_substitution_uses_the_original_equation_and_exact_values(self):
        check = mv.substitution_check("3x + 6 = 18", Fraction(4))
        self.assertEqual((check["left"], check["right"], check["leftValue"], check["ok"]), (r"3 \times 4 + 6", "18", "18", True))
        self.assertNotIn("\t", check["left"], "LaTeX backslash sequences must survive")
        self.assertEqual(mv.substitution_check("3x = -6", Fraction(-2))["left"], r"3 \times (-2)")
        self.assertTrue(mv.substitution_check("x/2 + 1 = 3", Fraction(4))["ok"])
        self.assertFalse(mv.substitution_check("3x + 6 = 18", Fraction(5))["ok"])


class TestTexAndTerms(unittest.TestCase):
    def test_terms_are_split_by_rank_not_guessed_from_glyphs(self):
        # « {} » force l'espacement d'un opérateur binaire au début d'un morceau
        self.assertEqual(ms.term_parts("3x + 6"), ["3x", "{}+ 6"])
        self.assertEqual(ms.term_parts("-2x - 5"), ["-2x", "{}- 5"])
        self.assertEqual(ms.term_parts("2(x+1) - 3"), ["2(x+1)", "{}- 3"])
        self.assertEqual(ms.term_parts("18"), ["18"])

    def test_simple_fractions_become_latex_fractions(self):
        self.assertEqual(ms.side_tex("(x+1)/2"), r"\frac{x+1}{2}")
        self.assertEqual(ms.side_tex("3 × 4"), r"3 \times 4")

    def test_cancelled_term_is_the_opposite_one(self):
        op = mv.describe_operation("3x + 6 = 18", "3x = 12")
        self.assertEqual(ms._cancel_index("3x + 6", op), 1)
        self.assertIsNone(ms._cancel_index("18", op))


class TestPlanTimeline(unittest.TestCase):
    def test_events_follow_the_real_voice(self):
        plan = ms.build_plan(SCENE, WORDS, 7.8)
        self.assertEqual(plan["timing"], "voice")
        first, second = plan["steps"][1]["events"], plan["steps"][2]["events"]
        self.assertAlmostEqual(first["showOp"], 1.66 - 0.12 - 0.12, delta=0.2, msg="op named with « retire »")
        self.assertLess(first["showOp"], first["sides"])
        self.assertLess(first["sides"], first["apply"])
        self.assertAlmostEqual(first["sides"], 2.36 - 0.12, delta=0.1, msg="« deux côtés »")
        self.assertAlmostEqual(first["apply"], 3.04 - 0.3, delta=0.35, msg="result when « trois x égale douze » is said")
        self.assertGreater(second["showOp"], first["apply"], "next operation after the previous result")
        self.assertGreater(second["apply"], 6.06, "result starts after the colon, not on « par trois »")

    def test_the_colon_marks_the_result_when_the_operation_has_a_complement(self):
        spoken = ms._spoken_tokens(WORDS)
        anchors = ms._anchors_for_step(spoken, SCENE["steps"][2], 0)
        self.assertGreaterEqual(anchors["result"], 6.7)

    def test_missing_anchor_falls_back_and_says_so(self):
        scene = {**SCENE, "steps": [*SCENE["steps"][:2], {**SCENE["steps"][2], "spoken": "phrase jamais prononcée"}]}
        plan = ms.build_plan(scene, WORDS, 9.0)
        self.assertEqual(plan["timing"], "fallback")
        self.assertIn("voice_anchor_missing:step3", plan["warnings"])
        events = [s["events"] for s in plan["steps"][1:]]
        self.assertTrue(all(e["showOp"] < e["sides"] < e["apply"] for e in events))
        self.assertLess(events[0]["apply"], events[1]["showOp"])

    def test_no_words_means_fallback_without_inventing_voice_sync(self):
        plan = ms.build_plan(SCENE, None, 9.0)
        self.assertEqual(plan["timing"], "fallback")
        self.assertEqual(ms.extra_hold_seconds(SCENE, None, 9.0), 0.0)

    def test_a_voice_that_is_too_fast_is_reported_not_compressed_under_the_floor(self):
        words = [dict(w, start=w["start"] / 4, end=w["end"] / 4) for w in WORDS]
        plan = ms.build_plan(SCENE, words, 2.0)
        floors = plan["rhythm"]
        for step in plan["steps"][1:]:
            ev = step["events"]
            self.assertGreaterEqual(ev["sides"] - ev["showOp"], floors["op_to_sides_min"] - 1e-6)
            self.assertGreaterEqual(ev["apply"] - ev["sides"], floors["sides_to_apply_min"] - 1e-6)
        self.assertTrue(any(w.startswith(("rhythm_tight", "duration_short")) for w in plan["warnings"]))

    def test_the_result_gets_reading_time_through_padding_not_compression(self):
        plan = ms.build_plan(SCENE, WORDS, 7.8)
        self.assertGreaterEqual(plan["neededDuration"], plan["steps"][2]["events"]["apply"] + plan["rhythm"]["apply_anim"] + plan["rhythm"]["result_hold"] - 1e-6)
        extra = ms.extra_hold_seconds(SCENE, WORDS, 7.8)
        self.assertGreater(extra, 0.5)
        self.assertGreaterEqual(7.8 + extra, plan["neededDuration"] - 0.01)

    def test_rhythm_is_configurable_and_bounded(self):
        with mock.patch.dict(os.environ, {"MATH_RHYTHM_JSON": '{"result_hold": 3, "op_in": 99, "unknown": 1}'}):
            rhythm = ms.rhythm_for({})
        self.assertEqual(rhythm["result_hold"], 3.0)
        self.assertEqual(rhythm["op_in"], ms.RHYTHM["op_in"], "out-of-range value ignored")
        self.assertNotIn("unknown", rhythm)

    def test_verification_is_planned_from_the_original_equation_only_when_requested(self):
        self.assertIsNone(ms.build_plan(SCENE, WORDS, 7.8)["verification"])
        scene = {**SCENE, "verify": True}
        plan = ms.build_plan(scene, WORDS, 7.8)
        sub = plan["verification"]["substitution"]
        self.assertTrue(sub["ok"])
        self.assertEqual(sub["left"], r"3 \times 4 + 6")
        self.assertGreater(plan["verification"]["at"], plan["steps"][2]["events"]["apply"])

    def test_intermediate_line_writes_the_operation_on_both_sides(self):
        step = ms.build_plan(SCENE, WORDS, 7.8)["steps"][1]
        self.assertEqual(step["intermediate"]["left"], "3x + 6 -6")
        self.assertEqual(step["intermediate"]["right"], "18 -6")
        self.assertEqual(step["cancel"], {"left": 1, "right": None})
        divide = ms.build_plan(SCENE, WORDS, 7.8)["steps"][2]
        self.assertEqual(divide["intermediate"]["left"], r"\frac{3x}{3}")

    def test_a_rewrite_step_has_no_sides_interval_so_it_follows_the_voice_closely(self):
        scene = {"sceneType": "equation_steps", "steps": [
            {"equation": "2(x + 3) = 14"},
            {"equation": "2x + 6 = 14", "spoken": "on développe"},
            {"equation": "2x = 8", "spoken": "on retire six"}]}
        words = [{"text": "On", "start": 0.0, "end": 0.1}, {"text": "développe", "start": 0.12, "end": 0.6},
                 {"text": ":", "start": 0.62, "end": 0.65}, {"text": "deux", "start": 0.7, "end": 0.9},
                 {"text": "x", "start": 0.92, "end": 1.0}, {"text": "plus", "start": 1.0, "end": 1.2},
                 {"text": "six", "start": 1.2, "end": 1.5}, {"text": "égale", "start": 1.5, "end": 1.8},
                 {"text": "quatorze.", "start": 1.8, "end": 2.4}, {"text": "On", "start": 2.6, "end": 2.7},
                 {"text": "retire", "start": 2.72, "end": 3.0}, {"text": "six", "start": 3.02, "end": 3.2},
                 {"text": "des", "start": 3.22, "end": 3.3}, {"text": "deux", "start": 3.32, "end": 3.4},
                 {"text": "côtés", "start": 3.42, "end": 3.7}, {"text": ":", "start": 3.72, "end": 3.75},
                 {"text": "deux", "start": 3.9, "end": 4.1}, {"text": "x", "start": 4.1, "end": 4.2},
                 {"text": "égale", "start": 4.2, "end": 4.4}, {"text": "huit.", "start": 4.4, "end": 4.9}]
        plan = ms.build_plan(scene, words, 6.0)
        rewrite = plan["steps"][1]
        self.assertNotIn("intermediate", rewrite)
        self.assertAlmostEqual(rewrite["events"]["apply"], 0.7 - 0.3, delta=0.2, msg="result when the voice says it")
        self.assertEqual(rewrite["events"]["sides"], rewrite["events"]["showOp"])
        self.assertEqual([w for w in plan["warnings"] if w.startswith("rhythm_tight:step2")], [])

    def test_unsupported_branch_line_is_kept_as_a_single_centered_line(self):
        scene = {"sceneType": "equation_steps", "steps": [
            {"equation": "x^2 - 5x + 6 = 0"}, {"equation": "(x - 2)(x - 3) = 0", "spoken": "on factorise"},
            {"equation": "x = 2 ou x = 3", "spoken": "produit nul"}]}
        plan = ms.build_plan(scene, None, 12.0)
        self.assertIsNone(plan["steps"][2]["left"])
        self.assertIn("ou", plan["steps"][2]["line"])
        self.assertEqual(plan["steps"][0]["validation"]["status"], "verified")


class TestValidationRisks(unittest.TestCase):
    @staticmethod
    def steps(*equations):
        return [{"equation": equation} for equation in equations]

    def test_dividing_by_x_does_not_silently_lose_the_zero_root(self):
        result = mv.verify_steps(self.steps("x(x - 2) = 0", "x - 2 = 0", "x = 2"))
        self.assertEqual(result["status"], "invalid")
        self.assertIn("x = 0", result["reason"])
        self.assertEqual(mv.verify_steps(self.steps("x(x - 2) = 0", "x = 2"))["status"], "invalid")

    def test_both_branches_are_accepted_for_a_product_equal_to_zero(self):
        result = mv.verify_steps(self.steps("x(x - 2) = 0", "x = 0 ou x = 2"))
        self.assertEqual((result["status"], result["solution"]), ("verified", ["0", "2"]))

    def test_rational_equation_with_a_polynomial_numerator_is_refused_not_approved(self):
        result = mv.verify_steps(self.steps("(x^2 - 1)/(x - 1) = 2", "x + 1 = 2", "x = 1"))
        self.assertEqual(result["status"], "unverified")

    def test_forbidden_value_is_kept_for_linear_denominators(self):
        result = mv.verify_steps(self.steps("1/(x - 1) = 2", "1 = 2(x - 1)", "1 = 2x - 2", "x = 3/2"))
        self.assertNotEqual(result["status"], "verified", "skipped operations are not approved")
        direct = mv.verify_steps(self.steps("(x - 1)/(x - 1) = 0", "x - 1 = 0"))
        self.assertNotEqual(direct["status"], "verified")

    def test_no_solution_and_infinite_solutions_are_distinguished(self):
        self.assertEqual(mv.verify_steps(self.steps("x + 1 = x + 2", "1 = 2"))["solutionKind"], "empty")
        self.assertEqual(mv.verify_steps(self.steps("2x + 2 = 2(x + 1)", "x + 1 = x + 1"))["solutionKind"], "identity")

    def test_false_step_and_skipped_operations_are_rejected(self):
        self.assertEqual(mv.verify_steps(self.steps("3x + 6 = 18", "3x = 13"))["status"], "invalid")
        self.assertEqual(mv.verify_steps(self.steps("3x + 6 = 18", "x = 4"))["status"], "unverified")


class TestDisplayTitle(unittest.TestCase):
    def test_variables_and_expressions_keep_their_case_while_words_are_upper_cased(self):
        from engine.motion_graphics.display_text import display_title

        self.assertEqual(display_title("Isoler x"), "ISOLER x")
        self.assertEqual(display_title("x ≠ 1"), "x ≠ 1")
        self.assertEqual(display_title("Résoudre 2(x + 3) = 14"), "RÉSOUDRE 2(x + 3) = 14")
        self.assertEqual(display_title("y = 2x + 1"), "y = 2x + 1")
        self.assertEqual(display_title("Second degré"), "SECOND DEGRÉ")
        self.assertEqual(display_title("Dix-huit"), "DIX-HUIT", "a hyphenated word is still a word")
        self.assertEqual(display_title(""), "")


if __name__ == "__main__":
    unittest.main()
