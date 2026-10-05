"""Mathematical correctness and visual integration for worked equations."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import assembler, script, visuals, voices
from engine.motion_graphics import preflight, schema, sync
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

    def test_wrong_step_requires_review(self):
        wrong = [*STEPS[:2], {"equation": "x = 5"}]
        self.assertEqual(verify_steps(wrong)["status"], "invalid")

    def test_nonlinear_and_unsupported_are_not_approved(self):
        for equation in ("x^2=4", "x*x=4", "sin(x)=0", "1/(x-1)=2"):
            with self.assertRaises(UnsupportedMath):
                solution_set(equation)
        self.assertEqual(verify_steps([{"equation": "x^2=4"}, {"equation": "x=2"}])["status"], "unverified")

    def test_identity_and_no_solution(self):
        self.assertEqual(solution_set("x+1=x+1"), ("identity", None))
        self.assertEqual(solution_set("x+1=x+2"), ("empty", None))


class TestEquationScene(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
