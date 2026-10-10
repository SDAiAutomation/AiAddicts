"""D7 de l'audit voix / visuel : le point d'un graphe et son « y = … » apparaissent quand la voix dit x puis y.

Le bloc est celui du benchmark maths : « À x égale quatre, la droite atteint onze. » (quatre à 3,71 s, onze à 5,0 s)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

from engine.motion_graphics import layout, manim_backend, sync
from engine.motion_graphics.scenes import RENDERERS
from engine.motion_graphics.theme import resolve_theme

WORDS = [
    {"text": text, "start": start, "end": start + 0.3}
    for text, start in (
        ("On", 0.0), ("peut", 0.19), ("aussi", 0.36), ("le", 0.57), ("voir", 0.67), ("sur", 0.88), ("le", 1.02),
        ("graphe", 1.13), ("de", 1.44), ("y", 1.71), ("égale", 1.76), ("deux", 2.09), ("x", 2.37), ("plus", 2.45),
        ("trois.", 2.6), ("À", 3.06), ("x", 3.34), ("égale", 3.45), ("quatre,", 3.71), ("la", 4.12), ("droite", 4.25),
        ("atteint", 4.62), ("onze.", 5.0),
    )
]
DURATION = 5.619
GRAPH = {"sceneType": "function_graph", "title": "La même réponse en image", "slope": 2, "intercept": 3,
         "xMin": 0, "xMax": 5, "yMin": 0, "yMax": 12, "highlightX": 4}


class TestWordValue(unittest.TestCase):
    def test_digits_and_number_words_in_french_and_english(self):
        cases = {"11": 11, "$150": 150, "onze.": 11, "Quatre,": 4, "dix-sept": 17, "vingt-trois": 23, "soixante-dix": 70,
                 "soixante-et-onze": 71, "quatre-vingts": 80, "quatre-vingt-dix": 90, "Eleven": 11, "twenty-three": 23,
                 "seven": 7}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(sync.word_value(text), expected)

    def test_ordinary_words_and_ambiguous_articles_are_not_numbers(self):
        for text in ("x", "égale", "la", "un", "une", "one", "plus", "1234"):
            with self.subTest(text=text):
                self.assertIsNone(sync.word_value(text))


class TestGraphAnchors(unittest.TestCase):
    def test_x_then_y_are_anchored_on_the_spoken_words(self):
        anchors = sync.graph_anchors(GRAPH, WORDS, DURATION)
        self.assertAlmostEqual(anchors["_graphX"] * DURATION, 3.71 - sync.LEAD_SECONDS, places=1)
        self.assertAlmostEqual(anchors["_graphY"] * DURATION, 5.0 - sync.LEAD_SECONDS, places=1)

    def test_attach_reveals_carries_them_without_touching_the_script_fields(self):
        out = sync.attach_reveals(GRAPH, WORDS, DURATION)
        self.assertIn("_graphX", out)
        self.assertEqual({k: out[k] for k in GRAPH}, GRAPH)

    def test_a_value_already_said_in_the_formula_does_not_count(self):
        # x = 2 : « deux » est dit dans la formule (2,09 s) puis dans « À x égale deux »
        graph = {**GRAPH, "highlightX": 2}   # y = 7
        words = [dict(w) for w in WORDS]
        words[18] = {"text": "deux,", "start": 3.71, "end": 4.0}
        words[22] = {"text": "sept.", "start": 5.0, "end": 5.3}
        anchors = sync.graph_anchors(graph, words, DURATION)
        self.assertAlmostEqual(anchors["_graphX"] * DURATION, 3.71 - sync.LEAD_SECONDS, places=1)

    def test_digits_are_recognised_too(self):
        words = [dict(w) for w in WORDS]
        words[18] = {"text": "4,", "start": 3.71, "end": 4.0}
        words[22] = {"text": "11.", "start": 5.0, "end": 5.3}
        anchors = sync.graph_anchors(GRAPH, words, DURATION)
        self.assertEqual(set(anchors), {"_graphX", "_graphY"})

    def test_nothing_safe_means_no_anchor(self):
        self.assertEqual(sync.graph_anchors(GRAPH, [], DURATION), {})
        self.assertEqual(sync.graph_anchors({**GRAPH, "highlightX": 2.5}, WORDS, DURATION), {})
        self.assertEqual(sync.graph_anchors({k: v for k, v in GRAPH.items() if k != "highlightX"}, WORDS, DURATION), {})
        self.assertIs(sync.attach_reveals(GRAPH, [{"text": "rien", "start": 0.0}], DURATION), GRAPH)

    def test_only_one_value_said_gives_only_that_anchor(self):
        only_y = [w for w in WORDS if w["text"] != "quatre,"]
        anchors = sync.graph_anchors(GRAPH, only_y, DURATION)
        self.assertEqual(set(anchors), {"_graphY"})


class TestGraphRendering(unittest.TestCase):
    SIZE = (540, 960)

    def _frame(self, scene, t):
        return RENDERERS["function_graph"](scene, t, resolve_theme(None), self.SIZE)

    def _label_row(self, image, left, right):
        w, h = self.SIZE
        return image.crop((round(w * left), round(h * 0.245), round(w * right), round(h * 0.29))).tobytes()

    def test_nothing_of_the_point_before_x_is_said(self):
        staged = {**GRAPH, "_graphX": 0.64, "_graphY": 0.87}
        bare = {k: v for k, v in GRAPH.items() if k != "highlightX"}
        self.assertEqual(self._frame(staged, 0.5).tobytes(), self._frame(bare, 0.5).tobytes())

    def test_y_stays_hidden_until_y_is_said_and_x_does_not_move(self):
        staged = {**GRAPH, "_graphX": 0.64, "_graphY": 0.87}
        bare = {k: v for k, v in GRAPH.items() if k != "highlightX"}
        between, before = self._frame(staged, 0.75), self._frame(bare, 0.75)
        self.assertNotEqual(self._label_row(between, 0.2, 0.5), self._label_row(before, 0.2, 0.5))   # « x = 4 » visible
        self.assertEqual(self._label_row(between, 0.62, 0.85), self._label_row(before, 0.62, 0.85))  # « y = 11 » absent, pas d'ombre
        after = self._frame(staged, 0.95)
        self.assertNotEqual(self._label_row(after, 0.62, 0.85), self._label_row(before, 0.62, 0.85))

    def test_final_state_is_identical_to_the_unstaged_scene(self):
        staged = {**GRAPH, "_graphX": 0.64, "_graphY": 0.87}
        self.assertEqual(self._frame(staged, 1.0).tobytes(), self._frame(GRAPH, 1.0).tobytes())

    def test_scene_without_anchors_is_unchanged(self):
        self.assertEqual(self._frame(GRAPH, 0.8).tobytes(), self._frame({**GRAPH}, 0.8).tobytes())
        self.assertNotEqual(self._frame(GRAPH, 0.8).tobytes(), self._frame(GRAPH, 0.3).tobytes())


class TestMaskedSegment(unittest.TestCase):
    def test_a_segment_without_colour_reserves_its_room_and_draws_nothing(self):
        def paint(segments):
            image = Image.new("RGB", (600, 80), "#000000")
            layout.draw_fitted_segments(ImageDraw.Draw(image), (300, 40), segments, 40, 560)
            return image

        full = paint([("x = 4", "#ffffff"), ("  →  y = 11", "#ffffff")])
        masked = paint([("x = 4", "#ffffff"), ("  →  y = 11", None)])
        left = (0, 0, 300, 80)
        self.assertEqual(masked.crop(left).tobytes(), full.crop(left).tobytes())       # « x = 4 » ne bouge pas
        self.assertIsNone(masked.crop((330, 0, 600, 80)).getbbox())                     # rien a droite
        self.assertIsNotNone(full.crop((330, 0, 600, 80)).getbbox())


class TestManimTimeline(unittest.TestCase):
    def test_without_anchors_the_historic_timing_is_kept(self):
        self.assertEqual(manim_backend.graph_timeline(GRAPH, 5.6, 3.3), (3.3, 3.3))

    def test_with_anchors_the_point_follows_x_and_y_follows_y(self):
        scene = {**GRAPH, "_graphX": 0.64, "_graphY": 0.87}
        dot, y = manim_backend.graph_timeline(scene, 5.6, 3.3)
        self.assertAlmostEqual(dot, 0.64 * 5.6, places=2)
        self.assertAlmostEqual(y, 0.87 * 5.6, places=2)

    def test_the_point_never_precedes_the_end_of_the_line_and_all_stays_in_the_block(self):
        scene = {**GRAPH, "_graphX": 0.1, "_graphY": 0.99}
        dot, y = manim_backend.graph_timeline(scene, 5.6, 3.3)
        self.assertEqual(dot, 3.3)
        self.assertLessEqual(y, 5.6 - 0.35 + 1e-9)
        self.assertGreaterEqual(y, dot)

    def test_only_x_anchored_shows_both_together(self):
        dot, y = manim_backend.graph_timeline({**GRAPH, "_graphX": 0.64}, 5.6, 3.3)
        self.assertEqual(dot, y)


if __name__ == "__main__":
    unittest.main()
