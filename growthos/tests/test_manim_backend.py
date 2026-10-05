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

    def test_graph_formula_reads_naturally(self):
        self.assertEqual(mb.graph_formula(2, 3), "y = 2x + 3")
        self.assertEqual(mb.graph_formula(1, -4), "y = x - 4")
        self.assertEqual(mb.graph_formula(-1, 0), "y = -x")
        self.assertEqual(mb.graph_formula(0, 5), "y = 5")


class TestEngineChoice(unittest.TestCase):
    def test_only_math_scenes_can_use_manim(self):
        with mock.patch.object(mb, "manim_installed", return_value=True), mock.patch.dict(os.environ, {"MATH_RENDERER": "auto"}):
            self.assertTrue(mb.wants(EQUATION))
            self.assertTrue(mb.wants({"sceneType": "function_graph", "slope": 1, "intercept": 0}))
            self.assertFalse(mb.wants({"sceneType": "icon_text", "text": "x"}))
            self.assertFalse(mb.wants({"sceneType": "big_number", "displayValue": "5"}))

    def test_pillow_can_be_forced_and_manim_must_be_installed(self):
        with mock.patch.object(mb, "manim_installed", return_value=True), mock.patch.dict(os.environ, {"MATH_RENDERER": "pillow"}):
            self.assertFalse(mb.wants(EQUATION))
        with mock.patch.object(mb, "manim_installed", return_value=False), mock.patch.dict(os.environ, {"MATH_RENDERER": "manim"}):
            self.assertFalse(mb.wants(EQUATION))

    def test_unknown_mode_falls_back_to_auto(self):
        with mock.patch.dict(os.environ, {"MATH_RENDERER": "nonsense"}):
            self.assertEqual(mb.renderer_mode(), "auto")


class TestFallbackToPillow(unittest.TestCase):
    def test_a_manim_failure_never_blocks_the_clip(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(mb, "wants", return_value=True), \
                mock.patch.object(mb, "render_clip", side_effect=RuntimeError("boom")):
            out = Path(tmp) / "clip.mp4"
            renderer.render_scene_clip(EQUATION, 1.0, str(out), resolution="270x480", fps=10)
            self.assertTrue(out.is_file() and out.stat().st_size > 1000, "the Pillow renderer took over")

    def test_pillow_is_used_when_manim_is_not_wanted(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(mb, "wants", return_value=False), \
                mock.patch.object(mb, "render_clip", side_effect=AssertionError("must not be called")):
            out = Path(tmp) / "clip.mp4"
            renderer.render_scene_clip(EQUATION, 1.0, str(out), resolution="270x480", fps=10)
            self.assertTrue(out.is_file())


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


if __name__ == "__main__":
    unittest.main()
