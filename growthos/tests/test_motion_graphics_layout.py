"""Phase 2.7 (global layout & caption collision system) — regression for the
exact production defect: a real Faceloop video's `comparison` scene drew
`optionA`/`optionB`'s `displayValue` ("Avoid audit risk" / "Chase refunds")
at a fixed font size with no width constraint, and the two values overflowed
their cards and collided in the middle of the frame. The fixture below is
the ACTUAL block from that content item (content_items.id
2b1c8f2f-f32f-4045-9fd5-a286d23b5d3c in the shared Supabase project), not a
synthetic approximation.
"""
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.motion_graphics import canvas, layout
from engine.motion_graphics.scenes import RENDERERS
from engine.motion_graphics.theme import resolve_theme

# The exact motion_graphic payload from the reported video's CTA block.
REAL_COMPARISON_SCENE = {
    "sceneType": "comparison",
    "title": "What would you choose?",
    "optionA": {"label": "Sell now", "displayValue": "Avoid audit risk"},
    "optionB": {"label": "Keep", "displayValue": "Chase refunds"},
}

SIZE = (1080, 1920)


class TestSafeZoneContractIsDerivedNotArbitrary(unittest.TestCase):
    def test_caption_reserved_ratio_covers_the_derived_worst_case(self):
        # margin_v=550 (largest across engine/captions.py's presets) + 2
        # wrapped lines at the tallest caption font (word_pop, 104px) * 1.2
        # line-height factor -> ~799.6px / 1920 ~= 0.4165. See
        # engine/motion_graphics/canvas.py's SAFE_BOTTOM_RATIO comment for
        # the full derivation this locks in.
        self.assertGreaterEqual(canvas.SAFE_BOTTOM_RATIO, 0.40)
        self.assertLessEqual(canvas.SAFE_BOTTOM_RATIO, 0.45)

    def test_content_zone_excludes_top_and_bottom_bands(self):
        x0, y0, x1, y1 = layout.content_zone(*SIZE)
        self.assertEqual((x0, x1), (0, SIZE[0]))
        self.assertGreater(y0, 0)
        self.assertLess(y1, SIZE[1])


class TestFitTextRespectsMaxWidth(unittest.TestCase):
    """Direct proof of the fix mechanism, using the EXACT reported strings
    and the EXACT geometry engine/motion_graphics/scenes.py::render_comparison
    uses (card box width, base font size)."""

    def _draw(self):
        return ImageDraw.Draw(Image.new("RGB", SIZE, "#000000"))

    def test_long_display_values_are_fit_within_the_card_width(self):
        draw = self._draw()
        w, h = SIZE
        box_a = (w * 0.08, h * 0.24, w * 0.46, h * 0.62)
        card_max_width = (box_a[2] - box_a[0]) * 0.86
        value_base_px = round(h * 0.045)
        for text in ("Avoid audit risk", "Chase refunds"):
            result = layout.fit_text(draw, text, value_base_px, card_max_width, bold=True)
            self.assertLessEqual(result.line_width, card_max_width + 1)

    def test_short_numeric_values_are_unaffected(self):
        # A short value ("$2,400") must render at the FULL base size, not be
        # shrunk unnecessarily — the fix must not degrade the common case.
        draw = self._draw()
        w, h = SIZE
        card_max_width = (w * 0.46 - w * 0.08) * 0.86
        value_base_px = round(h * 0.045)
        result = layout.fit_text(draw, "$2,400", value_base_px, card_max_width, bold=True)
        self.assertEqual(result.font.size, value_base_px)
        self.assertEqual(result.lines, ["$2,400"])


class TestComparisonSceneDoesNotCollideOnRealData(unittest.TestCase):
    """Renders the ACTUAL reported scene and checks real pixels — no
    designed-text color may appear in the gutter between the two cards,
    which is exactly where "Avoid audit risk" and "Chase refunds" collided
    in the original video."""

    def test_no_option_color_leaks_into_the_card_gutter(self):
        theme = resolve_theme(None)
        frame = RENDERERS["comparison"](REAL_COMPARISON_SCENE, 1.0, theme, SIZE)
        w, h = SIZE
        # The gutter between box_a (ends 0.46w) and box_b (starts 0.54w).
        gutter = frame.crop((round(w * 0.46), round(h * 0.24), round(w * 0.54), round(h * 0.62)))
        from engine.motion_graphics.theme import hex_to_rgb

        def matches(pixel, hex_color, tolerance=30):
            target = hex_to_rgb(hex_color)
            return all(abs(pixel[i] - target[i]) <= tolerance for i in range(3))

        leaked = [
            p for p in gutter.getdata()
            if matches(p, theme.primary) or matches(p, theme.accent)
        ]
        self.assertEqual(
            len(leaked), 0,
            f"{len(leaked)} pixel(s) of option-value colour leaked into the card gutter — "
            "this is the exact collision reported in production",
        )

    def test_frame_renders_without_raising(self):
        theme = resolve_theme(None)
        frame = RENDERERS["comparison"](REAL_COMPARISON_SCENE, 0.5, theme, SIZE)
        self.assertEqual(frame.size, SIZE)


class TestFindCollisions(unittest.TestCase):
    def test_overlapping_boxes_are_detected(self):
        boxes = {"a": (0, 0, 100, 100), "b": (50, 50, 150, 150), "c": (200, 200, 300, 300)}
        self.assertEqual(layout.find_collisions(boxes), [("a", "b")])

    def test_non_overlapping_boxes_are_clean(self):
        boxes = {"a": (0, 0, 50, 50), "b": (100, 100, 150, 150)}
        self.assertEqual(layout.find_collisions(boxes), [])

    def test_box_intruding_caption_zone_is_detected(self):
        w, h = SIZE
        zone = layout.caption_reserved_zone(w, h)
        intruding_box = (0, h * 0.55, w, h * 0.65)
        self.assertTrue(layout.intrudes_zone(intruding_box, zone))
        safe_box = (0, h * 0.3, w, h * 0.4)
        self.assertFalse(layout.intrudes_zone(safe_box, zone))


class TestTimelineLabelsStayInsideFrame(unittest.TestCase):
    """Phase 2.7 validation finding: the first timeline label ("Quarterly
    payment made", dot at 0.12w) was centred on its dot with a width wider
    than the distance to the frame edge and rendered clipped ("UARTERLY")."""

    def test_clamp_center_x_keeps_box_inside_margin(self):
        self.assertEqual(layout.clamp_center_x(130, 200, 1080, 54), 254)
        self.assertEqual(layout.clamp_center_x(950, 200, 1080, 54), 826)
        self.assertEqual(layout.clamp_center_x(540, 200, 1080, 54), 540)

    def test_real_timeline_has_no_designed_pixels_touching_frame_edges(self):
        theme = resolve_theme(None)
        scene = {
            "sceneType": "timeline", "title": "Refund timeline",
            "steps": ["Quarterly payment made", "Refund flagged", "Transfer pending"],
        }
        w, h = SIZE
        frame = RENDERERS["timeline"](scene, 1.0, theme, SIZE).convert("RGB")
        band = round(w * 0.03)
        y0, y1 = round(h * 0.40), round(h * 0.55)
        for x0, x1 in ((0, band), (w - band, w)):
            strip = frame.crop((x0, y0, x1, y1))
            brightest = max(sum(p) for p in strip.getdata())
            self.assertLess(brightest, 150, "label pixels reach the frame edge (clipped)")

    def test_adjacent_timeline_labels_do_not_touch(self):
        # Labels now alternate below/above the line (zigzag), so "adjacent"
        # is checked on the recorded text boxes, not a single pixel band.
        from engine.motion_graphics import preflight

        theme = resolve_theme(None)
        for steps in (
            ["Quarterly payment made", "Refund flagged", "Transfer pending"],
            ["Two-year refund issued", "Separate week flagged", "Audit pending"],
            ["Snap photos now", "Save originals to cloud", "Email to your agent"],
        ):
            scene = {"sceneType": "timeline", "title": "T", "steps": steps}
            result = preflight.check_scene(scene, theme, SIZE)
            self.assertEqual(result["errors"], [], f"{steps}: {result['errors']}")


class TestDensityGuard(unittest.TestCase):
    def test_rows_fit_within_available_height_are_unchanged(self):
        self.assertEqual(layout.max_rows_for_height(1000, 4), 4)

    def test_rows_are_capped_when_they_would_be_unreadable(self):
        # 1000px / 30 rows would be ~33px/row, below the legibility floor.
        capped = layout.max_rows_for_height(1000, 30)
        self.assertLess(capped, 30)
        self.assertGreaterEqual(capped, 1)


if __name__ == "__main__":
    unittest.main()
