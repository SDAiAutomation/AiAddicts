"""Rendu Manim des scènes maths : fonctions pures, choix du moteur, repli Pillow, et rendu réel si installé."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.motion_graphics import manim_backend as mb
from engine.motion_graphics import renderer


EQUATION = {"sceneType": "equation_steps", "title": "Isoler x", "steps": [
    {"equation": "3x - 5 = 10", "explanation": "Départ"},
    {"equation": "3x = 15", "explanation": "Ajouter 5"},
    {"equation": "x = 5", "explanation": "Diviser par 3"},
]}


class TestPureHelpers(unittest.TestCase):
    def test_tex_tokens_keep_the_token_count_of_the_plain_equation(self):
        for equation in ("3x - 5 = 10", "2*x + 3 = 11", "x = 8 ÷ (−2)", "2 × 4 + 3 = 11"):
            self.assertEqual(len(mb.tex_tokens(equation)), len(equation.split()), equation)
        self.assertEqual(mb.tex_tokens("x = 8 ÷ (−2)"), ["x", "=", "8", r"\div", "(-2)"])
        self.assertEqual(mb.tex_tokens("2*x = 8"), ["2x", "=", "8"])

    def test_line_segment_is_clipped_to_the_window(self):
        self.assertEqual(mb.line_segment(2, 3, 0, 5, 0, 12), (0, 4.5))
        self.assertEqual(mb.line_segment(-1, 4, 0, 10, 0, 4), (0, 4))
        self.assertEqual(mb.line_segment(0, 2, 0, 5, 0, 4), (0, 5))
        self.assertIsNone(mb.line_segment(0, 9, 0, 5, 0, 4))
        self.assertIsNone(mb.line_segment(1, 100, 0, 5, 0, 10))

    def test_reveal_times_follow_the_voice_and_never_start_on_an_empty_frame(self):
        times = mb.reveal_times({"_reveals": [0.12, 0.3, 0.62]}, 3, 8.0)
        self.assertEqual(times[0], 0.0, "first step is on screen from frame 1")
        self.assertAlmostEqual(times[1], 2.4)
        self.assertAlmostEqual(times[2], 4.96)
        even = mb.reveal_times({}, 3, 9.0)
        self.assertEqual(even[0], 0.0)
        self.assertTrue(all(b > a for a, b in zip(even, even[1:])))

    def test_reveal_times_keep_a_minimum_gap_between_steps(self):
        times = mb.reveal_times({"_reveals": [0.0, 0.01, 0.011]}, 3, 5.0)
        self.assertGreaterEqual(times[1] - times[0], 0.35)
        self.assertGreaterEqual(times[2] - times[1], 0.35)

    def test_typographic_minus_reads_as_a_minus_without_touching_compound_words(self):
        self.assertEqual(mb.typographic_minus("\u22124 des deux côtés"), "\u20134 des deux côtés")
        self.assertEqual(mb.typographic_minus("÷(-2) des deux côtés"), "÷(\u20132) des deux côtés")
        self.assertEqual(mb.typographic_minus("x = -3   y = -1.5"), "x = \u20133   y = \u20131.5")
        self.assertEqual(mb.typographic_minus("dix-huit"), "dix-huit")
        self.assertEqual(mb.typographic_minus("1-2"), "1-2", "a hyphen after a digit stays as written")
        self.assertEqual(mb.typographic_minus(""), "")

    def test_graph_formula_reads_naturally(self):
        self.assertEqual(mb.graph_formula(2, 3), "y = 2x + 3")
        self.assertEqual(mb.graph_formula(1, -4), "y = x - 4")
        self.assertEqual(mb.graph_formula(-1, 0), "y = -x")
        self.assertEqual(mb.graph_formula(0, 5), "y = 5")


class TestEngineChoice(unittest.TestCase):
    def test_only_math_scenes_can_use_manim(self):
        with mock.patch.object(mb, "manim_installed", return_value=True),                 mock.patch.object(mb, "latex_available", return_value=True),                 mock.patch.dict(os.environ, {"MATH_RENDERER": "auto"}):
            self.assertTrue(mb.wants(EQUATION))
            self.assertTrue(mb.wants({"sceneType": "function_graph", "slope": 1, "intercept": 0}))
            self.assertFalse(mb.wants({"sceneType": "icon_text", "text": "x"}))
            self.assertFalse(mb.wants({"sceneType": "big_number", "displayValue": "5"}))

    def test_auto_mode_needs_latex_for_equations_but_not_for_graphs(self):
        with mock.patch.object(mb, "manim_installed", return_value=True),                 mock.patch.object(mb, "latex_available", return_value=False),                 mock.patch.dict(os.environ, {"MATH_RENDERER": "auto"}):
            self.assertFalse(mb.wants(EQUATION), "no LaTeX: no Manim equation, the simplified render says so")
            self.assertTrue(mb.wants({"sceneType": "function_graph", "slope": 1, "intercept": 0}))

    def test_pillow_can_be_forced(self):
        with mock.patch.object(mb, "manim_installed", return_value=True), mock.patch.dict(os.environ, {"MATH_RENDERER": "pillow"}):
            self.assertFalse(mb.wants(EQUATION))

    def test_final_quality_mode_always_asks_for_manim_and_reports_what_is_missing(self):
        with mock.patch.object(mb, "manim_installed", return_value=False),                 mock.patch.object(mb.shutil, "which", return_value=None),                 mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            self.assertTrue(mb.wants(EQUATION))
            report = mb.dependency_report()
            self.assertFalse(report["ok"])
            self.assertTrue(any("manim" in item for item in report["missing"]))
            with self.assertRaises(mb.MathRenderError) as caught:
                mb.assert_ready_for_final([EQUATION])
            self.assertIn("dépendances manquantes", str(caught.exception))

    def test_preflight_ignores_other_modes_and_non_math_scenes(self):
        with mock.patch.object(mb, "manim_installed", return_value=False), mock.patch.dict(os.environ, {"MATH_RENDERER": "auto"}):
            mb.assert_ready_for_final([EQUATION])
        with mock.patch.object(mb, "manim_installed", return_value=False), mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            mb.assert_ready_for_final([{"sceneType": "icon_text", "text": "x"}, None])

    def test_unknown_mode_falls_back_to_auto(self):
        with mock.patch.dict(os.environ, {"MATH_RENDERER": "nonsense"}):
            self.assertEqual(mb.renderer_mode(), "auto")

    def test_render_error_is_not_swallowed_by_the_tolerant_runtime_error_handlers(self):
        self.assertFalse(issubclass(mb.MathRenderError, RuntimeError))


class TestLayoutGate(unittest.TestCase):
    def test_final_quality_mode_refuses_a_real_layout_overflow(self):
        with mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            for note in ("out_of_frame_x", "out_of_content_zone_y", "history_overlap", "history_overlaps_equation"):
                with self.assertRaises(mb.MathRenderError, msg=note):
                    mb.assert_layout_ok({"notes": [note]})
            mb.assert_layout_ok({"notes": ["small_equation_scale:1.1"], "info": ["balanced_equation:1.9"]})
            mb.assert_layout_ok({})

    def test_other_modes_only_report_the_overflow(self):
        for mode in ("auto", "pillow"):
            with mock.patch.dict(os.environ, {"MATH_RENDERER": mode}):
                mb.assert_layout_ok({"notes": ["out_of_frame_x"]})


class TestFallbackToPillow(unittest.TestCase):
    def test_auto_mode_failure_falls_back_and_records_the_reason(self):
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.dict(os.environ, {"MATH_RENDERER": "auto"}),                 mock.patch.object(mb, "wants", return_value=True),                 mock.patch.object(mb, "render_clip", side_effect=RuntimeError("boom")):
            out = Path(tmp) / "clip.mp4"
            renderer.render_scene_clip(EQUATION, 1.0, str(out), resolution="270x480", fps=10)
            self.assertTrue(out.is_file() and out.stat().st_size > 1000, "the Pillow renderer took over")
            report = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))
            self.assertEqual((report["engine"], report["requestedEngine"], report["simplified"]), ("pillow", "auto", True))
            self.assertIn("boom", report["fallbackReason"])

    def test_final_quality_mode_never_degrades_silently(self):
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}),                 mock.patch.object(mb, "wants", return_value=True),                 mock.patch.object(mb, "render_clip", side_effect=RuntimeError("latex exploded")):
            out = Path(tmp) / "clip.mp4"
            with self.assertRaises(mb.MathRenderError) as caught:
                renderer.render_scene_clip(EQUATION, 1.0, str(out), resolution="270x480", fps=10)
            self.assertIn("latex exploded", str(caught.exception))
            self.assertFalse(out.exists(), "no simplified clip is produced behind the caller's back")

    def test_pillow_is_used_when_manim_is_not_wanted(self):
        with tempfile.TemporaryDirectory() as tmp,                 mock.patch.dict(os.environ, {"MATH_RENDERER": "pillow"}),                 mock.patch.object(mb, "wants", return_value=False),                 mock.patch.object(mb, "render_clip", side_effect=AssertionError("must not be called")):
            out = Path(tmp) / "clip.mp4"
            renderer.render_scene_clip(EQUATION, 1.0, str(out), resolution="270x480", fps=10)
            self.assertTrue(out.is_file())
            report = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))
            self.assertEqual(report["fallbackReason"], "MATH_RENDERER=pillow")


class TestQueueDetection(unittest.TestCase):
    """scripts/queue_needs_manim.py : le worker n'installe Manim + LaTeX que pour un épisode de maths en file."""

    def setUp(self):
        import runpy
        self.module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "queue_needs_manim.py"))

    def test_only_math_scenes_trigger_the_install(self):
        has = self.module["has_math_scene"]
        self.assertTrue(has({"blocks": [{"text": "a"}, {"motion_graphic": {"sceneType": "equation_steps"}}]}))
        self.assertTrue(has({"blocks": [{"motion_graphic": {"sceneType": "function_graph"}}]}))
        self.assertFalse(has({"blocks": [{"motion_graphic": {"sceneType": "big_number"}}]}))
        self.assertFalse(has({"blocks": [{"text": "pas de scène"}]}))

    def test_malformed_scripts_never_raise(self):
        has = self.module["has_math_scene"]
        for script in (None, {}, {"blocks": None}, {"blocks": ["x", 3, None]}, {"blocks": [{"motion_graphic": "oops"}]}):
            self.assertFalse(has(script), repr(script))

    def test_a_database_error_means_pillow_not_a_failed_worker(self):
        with mock.patch.dict(self.module["main"].__globals__, {"queue_needs_manim": mock.Mock(side_effect=RuntimeError("db down"))}):
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": ""}):
                self.assertEqual(self.module["main"](), 0)

    def test_the_decision_is_written_to_github_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.txt"
            with mock.patch.dict(self.module["main"].__globals__, {"queue_needs_manim": mock.Mock(return_value=True)}), \
                    mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(target)}):
                self.assertEqual(self.module["main"](), 0)
            self.assertEqual(target.read_text(encoding="utf-8").strip(), "needs_manim=true")


@unittest.skipUnless(mb.manim_installed(), "manim non installé")
class TestRealManimRender(unittest.TestCase):
    def test_a_real_clip_has_the_exact_duration_and_size(self):
        import json
        import subprocess

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            out = Path(tmp) / "eq.mp4"
            scene = {**EQUATION, "_reveals": [0.0, 0.4, 0.7], "_duration": 4.0}
            renderer.render_scene_clip(scene, 4.0, str(out), resolution="540x960", fps=15)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out)],
                capture_output=True, text=True, check=True)
            info = json.loads(probe.stdout)
            self.assertAlmostEqual(float(info["format"]["duration"]), 4.0, delta=0.15)
            self.assertEqual((info["streams"][0]["width"], info["streams"][0]["height"]), (540, 960))

    def test_a_rewrite_followed_by_a_cancellation_renders_in_final_quality_mode(self):
        """Régression : après une réécriture (distribution), l'étape suivante annule un terme par son rang.
        Le mode manim est strict : un IndexError dans la scène lève MathRenderError au lieu d'un repli."""
        scene = {"sceneType": "equation_steps", "title": "Distribution", "steps": [
            {"equation": "2(x + 3) = 14", "explanation": "Objectif"},
            {"equation": "2x + 6 = 14", "explanation": "On distribue le 2"},
            {"equation": "2x = 8", "explanation": "−6 des deux côtés"},
            {"equation": "x = 4", "explanation": "÷2 des deux côtés"},
        ]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            out = Path(tmp) / "chain.mp4"
            renderer.render_scene_clip(scene, 14.0, str(out), resolution="270x480", fps=8)
            self.assertTrue(out.is_file() and out.stat().st_size > 1000)
            report = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))
            self.assertEqual(report["engine"], "manim")
            self.assertEqual(report["layout"]["notes"], [])

    def test_fraction_lines_do_not_overlap_in_the_history_and_the_verification_stays_in_the_zone(self):
        """Régression : une ligne avec fraction est deux fois plus haute ; l'historique à pas fixe se chevauchait."""
        scene = {"sceneType": "equation_steps", "title": "Une fraction", "verify": True, "steps": [
            {"equation": "x/2 + 1 = 3", "explanation": "Objectif"},
            {"equation": "x/2 = 2", "explanation": "−1 des deux côtés"},
            {"equation": "x = 4", "explanation": "×2 des deux côtés"},
        ]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            out = Path(tmp) / "fraction.mp4"
            renderer.render_scene_clip(scene, 14.0, str(out), resolution="270x480", fps=8)
            report = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))
            self.assertEqual(report["layout"]["notes"], [], "no history overlap, nothing outside the content zone")

    def test_a_branch_line_leaves_no_stray_equals_sign_from_the_previous_step(self):
        """Régression : le « = » de l'étape précédente restait sous « x = 2 ou x = 3 » (le « ou » paraissait barré)."""
        scene = {"sceneType": "equation_steps", "title": "Second degré", "steps": [
            {"equation": "x^2 - 5x + 6 = 0", "explanation": "Objectif"},
            {"equation": "(x - 2)(x - 3) = 0", "explanation": "On factorise"},
            {"equation": "x = 2 ou x = 3", "explanation": "Un produit est nul"},
        ]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            out = Path(tmp) / "quadratic.mp4"
            renderer.render_scene_clip(scene, 12.0, str(out), resolution="270x480", fps=8)
            layout = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))["layout"]
            self.assertEqual(layout["notes"], [])
            # titre + 2 lignes d'historique + la ligne finale + l'annotation
            self.assertEqual(layout["visibleOnScreen"], 5)
            self.assertTrue(any(info.startswith("balanced_equation") for info in layout["info"]),
                            "the asymmetric (x - 2)(x - 3) = 0 is balanced instead of shrunk")

    def test_four_fraction_steps_keep_the_boxed_result_clear_of_the_history(self):
        """Régression : le cadre du résultat final touchait la dernière ligne d'historique (restriction x ≠ 1)."""
        scene = {"sceneType": "equation_steps", "title": "x ≠ 1", "steps": [
            {"equation": "1/(x-1)=2", "explanation": "Valeur interdite : x ≠ 1"},
            {"equation": "1=2(x-1)", "explanation": "×(x − 1) des deux côtés"},
            {"equation": "1/2=x-1", "explanation": "÷2 des deux côtés"},
            {"equation": "3/2=x", "explanation": "+1 des deux côtés"},
        ]}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            out = Path(tmp) / "restriction.mp4"
            renderer.render_scene_clip(scene, 16.0, str(out), resolution="270x480", fps=8)
            layout = __import__("json").loads(Path(str(out) + ".render.json").read_text(encoding="utf-8"))["layout"]
            self.assertEqual(layout["notes"], [])


if __name__ == "__main__":
    unittest.main()
