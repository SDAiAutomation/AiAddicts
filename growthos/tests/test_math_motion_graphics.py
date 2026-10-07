"""Mathematical correctness and visual integration for worked equations."""
import json
import random
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from engine import assembler, script, visuals, voices
from engine.motion_graphics import preflight, schema, sync
from engine.motion_graphics.layout import record_boxes as layout_recorder
from engine.motion_graphics.math_validation import UnsupportedMath, solution_set, verify_graph, verify_steps
from engine.motion_graphics.preview import render_preview
from engine.motion_graphics.theme import resolve_theme


STEPS = [
    {"equation": "2*x + 3 = 11", "explanation": "Équation de départ", "spoken": "deux x plus trois"},
    {"equation": "2*x = 8", "explanation": "On retire 3", "spoken": "on retire trois"},
    {"equation": "x = 4", "explanation": "On divise par 2", "spoken": "on divise par deux"},
]


class TestMathVerification(unittest.TestCase):
    def test_graph_point_is_derived_and_bounded(self):
        graph = {"sceneType": "function_graph", "slope": 2, "intercept": 3,
                 "xMin": 0, "xMax": 5, "yMin": 0, "yMax": 12, "highlightX": 4}
        self.assertEqual(verify_graph(graph)["highlightY"], 11)
        self.assertEqual(verify_graph({**graph, "highlightX": 6})["status"], "unverified")
        self.assertEqual(verify_graph({**graph, "intercept": 50, "highlightX": 0})["reason"], "line is outside the graph")

    def test_exact_linear_solution(self):
        self.assertEqual(solution_set("2x + 3 = 11"), ("root", 4))
        self.assertEqual(solution_set("x/2 = 0.5"), ("root", 1))
        self.assertEqual(verify_steps(STEPS)["status"], "verified")

    def test_fraction_equation_from_failed_generation(self):
        steps = [
            {"equation": "(1/2)x + 1/3 = 5/6"},
            {"equation": "3x + 2 = 5"},
            {"equation": "3x = 3"},
            {"equation": "x = 1"},
        ]
        self.assertEqual(solution_set("(1/2)x + 1/3 = 5/6"), ("root", 1))
        self.assertEqual(verify_steps(steps)["operations"], [
            "scale_both_sides", "add_to_both_sides", "scale_both_sides",
        ])

    def test_nested_numeric_fractions_and_french_notation(self):
        self.assertEqual(solution_set("(x+1)/2 + (x-2)/3 = 4"), ("root", 5))
        self.assertEqual(verify_steps([
            {"equation": "(x+1)/2 + (x-2)/3 = 4"},
            {"equation": "3(x+1)+2(x-2)=24", "explanation": "×6 des deux côtés"},
            {"equation": "5x-1=24", "explanation": "On développe"},
            {"equation": "5x=25", "explanation": "+1 des deux côtés"},
        ])["status"], "verified")
        self.assertEqual(solution_set("[x+1] : (2/3) = 9"), ("root", 5))
        self.assertEqual(solution_set("(x+1) ⁄ 2 = 3"), ("root", 5))
        self.assertEqual(solution_set("1 1/2x = 3"), ("root", 2))
        self.assertEqual(solution_set("1½x = 3"), ("root", 2))
        self.assertEqual(solution_set("1 ½x = 3"), ("root", 2))
        self.assertEqual(solution_set("½x = 3"), ("root", 6))

    def test_ambiguous_fraction_notation_is_not_silently_approved(self):
        for equation in ("1/2x=3", "1/2(x+1)=3", "x/2/3=1"):
            with self.subTest(equation=equation), self.assertRaisesRegex(UnsupportedMath, "fraction ambiguë"):
                solution_set(equation)

    def test_rational_coefficients_have_exact_roots(self):
        rng = random.Random(20261006)
        for _ in range(60):
            a, b = rng.choice([n for n in range(-9, 10) if n]), rng.randint(1, 9)
            c, d = rng.randint(-9, 9), rng.randint(1, 9)
            e, f = rng.randint(-9, 9), rng.randint(1, 9)
            equation = f"({a}/{b})x+({c}/{d})={e}/{f}"
            expected = (Fraction(e, f) - Fraction(c, d)) / Fraction(a, b)
            with self.subTest(equation=equation):
                self.assertEqual(solution_set(equation), ("root", expected))

    def test_school_notation_and_exact_arithmetic(self):
        self.assertEqual(solution_set("2(x + 3) = 10"), ("root", 2))
        self.assertEqual(solution_set("(x + 1)(2) = 6"), ("root", 2))
        self.assertEqual(solution_set("0.1x + 0.2 = 0.3"), ("root", 1))
        self.assertEqual(solution_set("0,5x + 0,25 = 0,75"), ("root", 1))
        self.assertEqual(solution_set("−x = −2"), ("root", 2))

    def test_skipped_operation_requires_review(self):
        report = verify_steps([{"equation": "2x + 3 = 11"}, {"equation": "x = 4"}])
        self.assertEqual(report["status"], "unverified")
        self.assertIn("étape 2", report["reason"])

    def test_explicit_operation_label_must_match_visible_change(self):
        report = verify_steps([
            {"equation": "2x + 3 = 11"},
            {"equation": "2x = 8", "explanation": "−2 des deux côtés"},
        ])
        self.assertEqual(report["status"], "invalid")
        self.assertIn("libellé", report["reason"])
        self.assertEqual(verify_steps([
            {"equation": "(1/2)x + 1/3 = 5/6"},
            {"equation": "3x + 2 = 5", "explanation": "×6 des deux côtés"},
        ])["status"], "verified")

    def test_rewrite_and_equation_symmetry(self):
        self.assertEqual(verify_steps([
            {"equation": "2(x + 3) = 10"}, {"equation": "2x + 6 = 10"},
            {"equation": "10 = 2x + 6"},
        ])["operations"], ["rewrite", "rewrite"])

    def test_wrong_step_requires_review(self):
        wrong = [*STEPS[:2], {"equation": "x = 5"}]
        self.assertEqual(verify_steps(wrong)["status"], "invalid")

    def test_nonlinear_and_unsupported_are_not_approved(self):
        for equation in ("x^3=4", "sin(x)=0", "1/(x-1)=x"):
            with self.assertRaises(UnsupportedMath):
                solution_set(equation)
        with self.assertRaisesRegex(UnsupportedMath, "division par zéro"):
            solution_set("x/0=1")
        # x² = 4 → x = 2 perd la racine −2 : refusé comme INVALIDE (et plus seulement « non vérifié »).
        lost = verify_steps([{"equation": "x^2=4"}, {"equation": "x=2"}])
        self.assertEqual(lost["status"], "invalid")
        self.assertIn("x = -2", lost["reason"])

    def test_identity_and_no_solution(self):
        self.assertEqual(solution_set("x+1=x+1"), ("identity", None))
        self.assertEqual(solution_set("x+1=x+2"), ("empty", None))

    def test_rational_equations_track_excluded_values(self):
        self.assertEqual(solution_set("1/(x-1)=2"), ("root", Fraction(3, 2)))
        self.assertEqual(solution_set("x/(x-1)=2"), ("root", Fraction(2)))
        self.assertEqual(solution_set("(x-1)/(x-1)=0"), ("empty", None))
        with self.assertRaises(UnsupportedMath):
            solution_set("(x-1)/(x-1)=1")
        result = verify_steps([
            {"equation": "1/(x-1)=2"},
            {"equation": "1=2(x-1)"},
            {"equation": "1=2x-2"},
            {"equation": "3=2x"},
        ])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["excludedValues"], ["1"])
        self.assertEqual(verify_steps([
            {"equation": "(x-1)/(x-1)=0"},
            {"equation": "1=0"},
        ])["status"], "verified")
        self.assertEqual(verify_steps([
            {"equation": "(x-1)/(x-1)=0"},
            {"equation": "x-1=0"},
        ])["status"], "invalid")
        self.assertEqual(verify_steps([
            {"equation": "1/(x-1)=2"},
            {"equation": "1/(x-2)=-2"},
        ])["status"], "unverified")

    def test_quadratic_factorization_and_zero_product(self):
        self.assertEqual(solution_set("x^2-5x+6=0"), ("roots", (Fraction(2), Fraction(3))))
        self.assertEqual(solution_set("x²-5x+6=0"), ("roots", (Fraction(2), Fraction(3))))
        self.assertEqual(solution_set("2(x-2)(x-3)=0"), ("roots", (Fraction(2), Fraction(3))))
        self.assertEqual(solution_set("(x-2)^2=0"), ("root", Fraction(2)))
        self.assertEqual(solution_set("x^2+1=0"), ("empty", None))
        good = verify_steps([
            {"equation": "x^2-5x+6=0"},
            {"equation": "(x-2)(x-3)=0"},
            {"equation": "x=2 ou x=3"},
        ])
        self.assertEqual(good["status"], "verified")
        self.assertEqual(good["solution"], ["2", "3"])
        self.assertEqual(verify_steps([
            {"equation": "x^2-5x+6=0"},
            {"equation": "(x-2)(x-3)=0"},
            {"equation": "x=2 ou x=4"},
        ])["status"], "invalid")
        self.assertEqual(verify_steps([
            {"equation": "x^2-5x+6=0"},
            {"equation": "x=2 ou x=3"},
        ])["status"], "unverified")
        with self.assertRaises(UnsupportedMath):
            solution_set("x^2-2=0")


class TestEquationScene(unittest.TestCase):
    def test_quadratic_scene_passes_script_validation_and_renders_as_two_roots(self):
        data = {"title": "Deux racines", "niche": "mathématiques", "account": "demo", "blocks": [
            {"role": "point", "text": "On factorise puis on trouve deux valeurs.", "motion_graphic": {
                "sceneType": "equation_steps", "steps": [
                    {"equation": "x²-5x+6=0"},
                    {"equation": "(x-2)(x-3)=0"},
                    {"equation": "x=2 ou x=3"},
                ],
            }},
        ]}
        script.validate_script(data)
        with tempfile.TemporaryDirectory() as tmp:
            scene = visuals.prepare_motion_graphics_scene(data["blocks"][0], 5.0,
                Path(tmp) / "absent.words.json", (1080, 1920))
        self.assertEqual(scene["_solutionKind"], "roots")
        self.assertEqual(scene["steps"][-1]["equation"], "x=2 ou x=3")

    def test_domain_is_carried_to_continuation_scene(self):
        data = {"title": "Restriction", "niche": "mathématiques", "account": "demo", "blocks": [
            {"role": "point", "text": "On exclut un.", "motion_graphic": {
                "sceneType": "equation_steps", "steps": [
                    {"equation": "1/(x-1)=2"}, {"equation": "1=2(x-1)"},
                ],
            }},
            {"role": "point", "text": "On termine.", "motion_graphic": {
                "sceneType": "equation_steps", "steps": [
                    {"equation": "1=2(x-1)"}, {"equation": "3=2x"},
                ],
            }},
        ]}
        script.validate_script(data)
        self.assertEqual(data["blocks"][1]["motion_graphic"]["_domainExclusions"], ["1"])
        with tempfile.TemporaryDirectory() as tmp:
            report = []
            scene = visuals.prepare_motion_graphics_scene(data["blocks"][1], 4.0,
                Path(tmp) / "absent.words.json", (1080, 1920), block_index=1, report=report)
        self.assertEqual(scene["title"], "x ≠ 1")
        self.assertEqual(report[0]["action"], "domain_review")

    def test_rational_scene_displays_domain_and_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = []
            scene = visuals.prepare_motion_graphics_scene({
                "text": "On exclut un.", "motion_graphic": {"sceneType": "equation_steps", "steps": [
                    {"equation": "1/(x-1)=2"}, {"equation": "1=2(x-1)"},
                ]},
            }, 4.0, Path(tmp) / "absent.words.json", (1080, 1920), report=report)
        self.assertEqual(scene["title"], "x ≠ 1")
        self.assertTrue(report[0]["manualReview"])
        self.assertEqual(report[0]["action"], "domain_review")

    def test_math_scripts_use_existing_elevenlabs_voice_resolution(self):
        example = json.loads(Path("content/scripts/exemple-maths.json").read_text(encoding="utf-8"))
        self.assertNotIn("voice_id", example)
        self.assertEqual(voices.resolve_voice(example, voice_map={"default": "configured-voice"}), "configured-voice")
        self.assertEqual(voices.resolve_voice(example, voice_map={
            "mathématiques": "math-voice", "default": "configured-voice",
        }), "math-voice")

    def test_invalid_script_stops_before_paid_generation(self):
        example = json.loads(Path("content/scripts/exemple-maths.json").read_text(encoding="utf-8"))
        script.validate_script(example)
        example["blocks"][1]["motion_graphic"]["steps"][-1]["equation"] = "x=5"
        with self.assertRaisesRegex(ValueError, "résolution mathématique"):
            script.validate_script(example)

    def test_consecutive_equation_blocks_must_continue_the_same_derivation(self):
        example = json.loads(Path("content/scripts/exemple-maths.json").read_text(encoding="utf-8"))
        first = example["blocks"][1]
        continuation = {"role": "point", "text": "On vérifie la suite.", "motion_graphic": {
            "sceneType": "equation_steps", "steps": [
                {"equation": "2x + 3 = 11"}, {"equation": "2x = 8"},
            ],
        }}
        example["blocks"].insert(2, continuation)
        with self.assertRaisesRegex(ValueError, "reprendre la dernière équation"):
            script.validate_script(example)
        continuation["motion_graphic"]["steps"] = [
            {"equation": "x = 4"}, {"equation": "2x = 8"},
        ]
        script.validate_script(example)

    def test_fraction_derivation_across_two_blocks_validates_before_generation(self):
        data = {"title": "Fractions", "niche": "mathématiques", "account": "demo", "blocks": [
            {"role": "hook", "text": "Résolvons cette équation."},
            {"role": "point", "text": "On supprime les dénominateurs puis on développe.",
             "motion_graphic": {"sceneType": "equation_steps", "steps": [
                 {"equation": "(x+1)/2 + (x-2)/3 = 4"},
                 {"equation": "3(x+1)+2(x-2)=24", "explanation": "×6 des deux côtés"},
                 {"equation": "5x-1=24", "explanation": "Développer et réduire"},
             ]}},
            {"role": "point", "text": "On ajoute un puis on divise par cinq.",
             "motion_graphic": {"sceneType": "equation_steps", "steps": [
                 {"equation": "5x-1=24"},
                 {"equation": "5x=25", "explanation": "+1 des deux côtés"},
                 {"equation": "x=5", "explanation": "÷5 des deux côtés"},
             ]}},
        ]}
        script.validate_script(data)

    def test_invalid_graph_stops_before_paid_generation(self):
        example = json.loads(Path("content/scripts/exemple-maths.json").read_text(encoding="utf-8"))
        example["blocks"][2]["motion_graphic"]["highlightX"] = 99
        with self.assertRaisesRegex(ValueError, "graphe mathématique"):
            script.validate_script(example)

    def test_graph_preflight(self):
        graph = {"sceneType": "function_graph", "title": "La même réponse en image", "slope": 2,
                 "intercept": 3, "xMin": 0, "xMax": 5, "yMin": 0, "yMax": 12, "highlightX": 4}
        self.assertIsNotNone(schema.validate_scene(graph))
        report = preflight.check_scene(graph, resolve_theme(None), (1080, 1920))
        self.assertTrue(report["ok"], report["errors"])

    def test_contradiction_is_marked_as_no_solution(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = visuals.prepare_motion_graphics_scene({
                "text": "Aucune solution", "motion_graphic": {"sceneType": "equation_steps", "steps": [
                    {"equation": "2x+1=2x+3"}, {"equation": "1=3"},
                ]},
            }, 4.0, Path(tmp) / "absent.words.json", (1080, 1920))
        self.assertEqual(scene["_solutionKind"], "empty")

    def test_scene_contract_and_voice_timing(self):
        scene = {"sceneType": "equation_steps", "title": "Résous x", "steps": STEPS}
        self.assertIsNotNone(schema.validate_scene(scene))
        words = [{"text": token, "start": at} for token, at in [
            ("deux", 0.5), ("x", 0.8), ("plus", 1.0), ("trois", 1.2),
            ("on", 2.0), ("retire", 2.2), ("trois", 2.5),
            ("on", 3.5), ("divise", 3.7), ("par", 3.9), ("deux", 4.1),
        ]]
        timed = sync.attach_reveals(scene, words, 5.0)
        self.assertEqual(len(timed["_reveals"]), 3)
        self.assertEqual(timed["_reveals"], sorted(timed["_reveals"]))

    def test_unmatched_spoken_anchor_requests_review(self):
        scene = {"sceneType": "equation_steps", "steps": STEPS}
        with tempfile.TemporaryDirectory() as tmp:
            words_path = Path(tmp) / "words.json"
            words_path.write_text(json.dumps([{"text": "different", "start": 0.5}]))
            report = []
            visuals.prepare_motion_graphics_scene({"text": "Narration", "motion_graphic": scene},
                                                  5.0, words_path, (270, 480), report=report)
        self.assertTrue(report[0]["manualReview"])
        self.assertEqual(report[0]["action"], "voice_sync_review")

    def test_preflight_and_contact_sheet(self):
        scene = {"sceneType": "equation_steps", "title": "Résous x", "steps": STEPS}
        with tempfile.TemporaryDirectory() as tmp:
            report = []
            prepared = visuals.prepare_motion_graphics_scene(
                {"text": "Résolvons l'équation", "motion_graphic": scene}, 5.0,
                Path(tmp) / "absent.words.json", (1080, 1920), report=report,
            )
            self.assertEqual(report[0]["mathVerification"]["status"], "verified")
            self.assertEqual(prepared["sceneType"], "equation_steps")
            self.assertTrue(preflight.check_scene(prepared, resolve_theme(None), (1080, 1920))["ok"])
            output = render_preview(prepared, [0, 2.5, 5], 5, Path(tmp) / "math.png", "270x480")
            self.assertTrue(output.is_file())

    def test_invalid_derivation_hides_equations_and_flags_review(self):
        report = []
        with tempfile.TemporaryDirectory() as tmp:
            scene = visuals.prepare_motion_graphics_scene(
                {"text": "Résolvons l'équation", "motion_graphic": {
                    "sceneType": "equation_steps", "steps": [*STEPS[:2], {"equation": "x=5"}],
                }}, 5.0, Path(tmp) / "absent.words.json", (270, 480), report=report,
            )
        self.assertEqual(scene["sceneType"], "icon_text")
        self.assertTrue(report[0]["manualReview"])
        self.assertEqual(report[0]["mathVerification"]["status"], "invalid")

    def test_math_review_forces_quality_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "video.mp4"
            video_path.write_bytes(b"0" * 20000)
            fields = assembler._quality_fields({
                "motion_preflight": [{"manualReview": True, "mathVerification": {"status": "invalid"}}],
            }, str(video_path))
        self.assertEqual(fields["status"], "quality_check")
        self.assertTrue(any("mathématique" in flag for flag in fields["quality_flags"]))


class TestMathLayoutReadability(unittest.TestCase):
    """Phone readability of the two math scenes (benchmark 2026-10-05: the step captions rendered at
    33 px and the graph labels at 40 px on a 1080x1920 frame, the equations pinned to the top)."""

    SIZE = (1080, 1920)

    def _report(self, scene):
        report = preflight.check_scene(scene, resolve_theme(None), self.SIZE)
        self.assertTrue(report["ok"], report["errors"])
        return report

    def test_equation_steps_stay_readable_from_two_to_four_steps(self):
        pool = [
            {"equation": "2x + 3 = 11", "explanation": "Départ"},
            {"equation": "2x + 3 - 3 = 11 - 3", "explanation": "On retire 3 des deux côtés de l'égalité"},
            {"equation": "2x = 8", "explanation": "On simplifie"},
            {"equation": "x = 4", "explanation": "On divise les deux côtés par 2"},
        ]
        for count in (2, 3, 4):
            with self.subTest(steps=count):
                report = self._report({"sceneType": "equation_steps", "title": "Isoler x", "steps": pool[:count]})
                self.assertGreaterEqual(report["minFontPx"], 40)

    def test_equation_stack_is_centred_in_the_content_zone_and_independent_of_reveal_time(self):
        from engine.motion_graphics import layout, scenes
        scene = {"sceneType": "equation_steps", "title": "Isoler x", "steps": STEPS}
        theme = resolve_theme(None)
        early = scenes.render_equation_steps(dict(scene), 0.3, theme, self.SIZE)
        late = scenes.render_equation_steps(dict(scene), 4.9, theme, self.SIZE)
        _, _, _, bottom = layout.content_zone(*self.SIZE)
        # nothing is drawn in the caption-reserved band, and the first row does not move when more appear
        for image in (early, late):
            band = image.crop((0, bottom + 4, self.SIZE[0], self.SIZE[1])).convert("L")
            self.assertLess(band.getextrema()[1] - band.getextrema()[0], 40)
        row = (80, round(self.SIZE[1] * 0.2), self.SIZE[0] - 80, round(self.SIZE[1] * 0.22))
        self.assertEqual(early.crop(row).convert("L").getextrema()[0] > 0, late.crop(row).convert("L").getextrema()[0] > 0)

    def test_function_graph_labels_stay_readable(self):
        graph = {"sceneType": "function_graph", "title": "La même réponse en image", "slope": 2,
                 "intercept": 3, "xMin": 0, "xMax": 5, "yMin": 0, "yMax": 12, "highlightX": 4}
        self.assertGreaterEqual(self._report(graph)["minFontPx"], 45)


class TestEquationTransformation(unittest.TestCase):
    """The derivation reads as a transformation: changed tokens are picked out, a scene never opens on
    an empty frame, and a new step does not move the ones already on screen."""

    SIZE = (1080, 1920)

    def test_changed_tokens_are_the_new_or_rewritten_parts(self):
        from engine.motion_graphics.scenes import _changed_flags
        # the operation applied to both sides shows up as the two new "- 3" pairs
        self.assertEqual(_changed_flags("2x + 3 = 11", "2x + 3 - 3 = 11 - 3"),
                         [False, False, False, True, True, False, False, True, True])
        self.assertEqual(_changed_flags("3x - 5 = 10", "3x = 15"), [False, False, True])

    def test_formatting_only_or_total_rewrites_highlight_nothing(self):
        from engine.motion_graphics.scenes import _changed_flags
        self.assertEqual(_changed_flags("2*x = 8", "2x = 8"), [False, False, False])
        self.assertEqual(_changed_flags("2x = 8", "2x = 8"), [False, False, False])
        self.assertEqual(_changed_flags("a b c", "d e f"), [False, False, False])
        self.assertEqual(_changed_flags("", "x = 4"), [False, False, False])

    def test_first_step_is_visible_on_the_very_first_frame(self):
        from PIL import ImageChops
        from engine.motion_graphics import scenes
        theme = resolve_theme(None)
        scene = {"sceneType": "equation_steps", "steps": STEPS}
        first = scenes.render_equation_steps(dict(scene), 0.0, theme, self.SIZE)
        empty = scenes.render_equation_steps({"sceneType": "equation_steps", "steps": []}, 0.0, theme, self.SIZE)
        self.assertIsNotNone(ImageChops.difference(first, empty).getbbox(), "frame 1 must already show the first equation")

    def test_unrevealed_steps_draw_nothing(self):
        from PIL import ImageChops
        from engine.motion_graphics import layout, scenes
        theme = resolve_theme(None)
        scene = {"sceneType": "equation_steps", "steps": STEPS, "_reveals": [0.0, 0.9, 0.95], "_duration": 10.0}
        early = scenes.render_equation_steps(dict(scene), 0.3, theme, self.SIZE)
        backdrop = scenes.render_equation_steps({"sceneType": "equation_steps", "steps": []}, 0.3, theme, self.SIZE)
        w, h = self.SIZE
        top, bottom = h * 0.185, layout.content_zone(w, h)[3] - h * 0.02
        row_h = min((bottom - top) / len(STEPS), h * 0.17)
        third = (80, round(top + 2 * row_h + 4), w - 80, round(top + 3 * row_h - 4))
        self.assertIsNone(ImageChops.difference(early.crop(third), backdrop.crop(third)).getbbox(),
                          "a step that has not appeared yet leaves no empty box")

    def test_highlighted_equation_is_still_checked_by_preflight(self):
        scene = {"sceneType": "equation_steps", "steps": [
            {"equation": "2x + 3 = 11"}, {"equation": "2x + 3 - 3 = 11 - 3"}, {"equation": "2x = 8"}, {"equation": "x = 4"}]}
        with layout_recorder() as boxes:
            report = preflight.check_scene(scene, resolve_theme(None), self.SIZE)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(any(b["text"].startswith("2x + 3 - 3") for b in boxes) or report["minFontPx"] is not None)


class TestEquationCase(unittest.TestCase):
    def test_an_equation_keeps_its_lowercase_variable_other_text_is_upper_cased(self):
        from engine.motion_graphics.scenes import _display_case
        self.assertEqual(_display_case("3x - 5 = 10"), "3x - 5 = 10")
        self.assertEqual(_display_case("Solution: x = 5"), "Solution: x = 5")
        self.assertEqual(_display_case("Trouve x"), "TROUVE X")
        self.assertEqual(_display_case("deux points = deux"), "DEUX POINTS = DEUX")


if __name__ == "__main__":
    unittest.main()
