import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.motion_graphics import animations, schema, theme
from engine.motion_graphics.scenes import RENDERERS


class TestSchemaValidation(unittest.TestCase):
    def test_big_number_requires_display_value(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "big_number"}))
        self.assertIsNotNone(schema.validate_scene({"sceneType": "big_number", "displayValue": "$3,000"}))

    def test_unknown_scene_type_is_invalid(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "pie_of_the_sky", "displayValue": "x"}))

    def test_non_dict_is_invalid(self):
        self.assertIsNone(schema.validate_scene(None))
        self.assertIsNone(schema.validate_scene("big_number"))
        self.assertIsNone(schema.validate_scene(["big_number"]))

    def test_money_split_requires_nonempty_data_with_labels(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "money_split", "data": []}))
        self.assertIsNone(schema.validate_scene({"sceneType": "money_split", "data": [{"value": 100}]}))
        self.assertIsNotNone(
            schema.validate_scene(
                {"sceneType": "money_split", "data": [{"label": "Needs", "value": 1500, "displayValue": "$1,500"}]}
            )
        )

    def test_data_item_with_non_numeric_value_is_invalid(self):
        self.assertIsNone(
            schema.validate_scene({"sceneType": "bar_chart", "data": [{"label": "Rent", "value": "a lot"}]})
        )

    def test_progress_bar_requires_numeric_target_ratio(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "progress_bar", "displayValue": "$4,200 / $10,000"}))
        self.assertIsNone(
            schema.validate_scene({"sceneType": "progress_bar", "displayValue": "x", "targetRatio": "42%"})
        )
        self.assertIsNotNone(
            schema.validate_scene({"sceneType": "progress_bar", "displayValue": "x", "targetRatio": 0.42})
        )

    def test_comparison_requires_both_labelled_options(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "comparison", "optionA": {"label": "A"}}))
        self.assertIsNotNone(
            schema.validate_scene(
                {"sceneType": "comparison", "optionA": {"label": "A"}, "optionB": {"label": "B"}}
            )
        )

    def test_checklist_and_timeline_and_formula_need_nonempty_string_lists(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "checklist", "items": []}))
        self.assertIsNone(schema.validate_scene({"sceneType": "timeline", "steps": [""]}))
        self.assertIsNotNone(schema.validate_scene({"sceneType": "formula", "terms": ["INCOME", "= BUDGET"]}))

    def test_normalized_scene_type_accepts_legacy_type_key(self):
        self.assertEqual(schema.normalized_scene_type({"type": "warning", "title": "x"}), "warning")
        self.assertIsNone(schema.normalized_scene_type({"type": "not_a_scene"}))


class TestThemeDefaults(unittest.TestCase):
    def test_no_overrides_returns_default(self):
        self.assertIs(theme.resolve_theme(None), theme.DEFAULT_THEME)
        self.assertIs(theme.resolve_theme({}), theme.DEFAULT_THEME)

    def test_valid_override_replaces_field(self):
        resolved = theme.resolve_theme({"primary": "#00FF00"})
        self.assertEqual(resolved.primary, "#00FF00")
        self.assertEqual(resolved.background, theme.DEFAULT_THEME.background)

    def test_unknown_and_empty_overrides_are_ignored(self):
        resolved = theme.resolve_theme({"brand_name": "PocketLogic", "primary": ""})
        self.assertEqual(resolved, theme.DEFAULT_THEME)

    def test_hex_to_rgb_roundtrip(self):
        self.assertEqual(theme.hex_to_rgb("#FFFFFF"), (255, 255, 255))
        self.assertEqual(theme.hex_to_rgb("#fff"), (255, 255, 255))

    def test_lerp_color_endpoints(self):
        self.assertEqual(theme.lerp_color("#000000", "#FFFFFF", 0.0), (0, 0, 0))
        self.assertEqual(theme.lerp_color("#000000", "#FFFFFF", 1.0), (255, 255, 255))


class TestAnimationPrimitives(unittest.TestCase):
    def test_phase_is_held_outside_its_window(self):
        self.assertEqual(animations.phase(-1, 0.2, 0.5), 0.0)
        self.assertEqual(animations.phase(2, 0.2, 0.5), 1.0)

    def test_count_up_reaches_target_at_end(self):
        self.assertAlmostEqual(animations.count_up(1.0, target=3000, end=0.6), 3000)
        self.assertEqual(animations.count_up(0.0, target=3000, start=0.0, end=0.6), 0.0)

    def test_progress_fill_respects_target_ratio_cap(self):
        self.assertAlmostEqual(animations.progress_fill(1.0, target_ratio=0.42), 0.42)
        self.assertAlmostEqual(animations.progress_fill(1.0, target_ratio=1.4), 1.0)

    def test_format_like_preserves_prefix_and_grouping(self):
        self.assertEqual(animations.format_like("$3,000", 1500), "$1,500")
        self.assertEqual(animations.format_like("42%", 21), "21%")

    def test_parse_number_extracts_digits(self):
        self.assertEqual(animations.parse_number("$4,200 / $10,000"), 4200.0)
        self.assertIsNone(animations.parse_number("no digits here"))

    def test_stagger_orders_items_in_time(self):
        # Le premier élément doit être visible avant les suivants à un t donné.
        self.assertGreaterEqual(animations.stagger(0.3, 0, 4), animations.stagger(0.3, 3, 4))


_SAMPLE_SCENES = {
    "big_number": {"sceneType": "big_number", "title": "Monthly income", "displayValue": "$3,000", "value": 3000, "label": "Income"},
    "money_split": {
        "sceneType": "money_split",
        "displayValue": "$3,000",
        "data": [
            {"label": "Needs", "value": 1500, "displayValue": "$1,500"},
            {"label": "Wants", "value": 900, "displayValue": "$900"},
            {"label": "Savings", "value": 600, "displayValue": "$600"},
        ],
        "emphasis": "Savings",
    },
    "progress_bar": {"sceneType": "progress_bar", "title": "Emergency fund", "displayValue": "$4,200 / $10,000", "targetRatio": 0.42},
    "bar_chart": {
        "sceneType": "bar_chart",
        "data": [
            {"label": "Rent", "value": 1200, "displayValue": "$1,200"},
            {"label": "Food", "value": 450, "displayValue": "$450"},
        ],
    },
    "donut_chart": {
        "sceneType": "donut_chart",
        "data": [
            {"label": "Needs", "value": 50, "displayValue": "50%"},
            {"label": "Wants", "value": 30, "displayValue": "30%"},
            {"label": "Savings", "value": 20, "displayValue": "20%"},
        ],
    },
    "comparison": {
        "sceneType": "comparison",
        "optionA": {"label": "Option A", "displayValue": "$500/mo"},
        "optionB": {"label": "Option B", "displayValue": "$350/mo"},
    },
    "before_after": {
        "sceneType": "before_after",
        "before": {"label": "Before", "displayValue": "$0 saved"},
        "after": {"label": "After 12 months", "displayValue": "$3,600 saved"},
    },
    "timeline": {"sceneType": "timeline", "steps": ["Month 1", "Month 6", "Year 1", "Year 5"]},
    "compound_growth": {
        "sceneType": "compound_growth",
        "data": [
            {"label": "Start", "displayValue": "$100/mo"},
            {"label": "Year 1", "displayValue": "$1,200"},
            {"label": "Year 5", "displayValue": "$15,000+"},
        ],
    },
    "checklist": {"sceneType": "checklist", "items": ["Emergency fund", "Pay high-interest debt", "Start investing"]},
    "warning": {"sceneType": "warning", "title": "Don't do this", "label": "Money mistake #1"},
    "formula": {"sceneType": "formula", "terms": ["INCOME", "− SAVINGS", "= SPENDING BUDGET"]},
    "icon_text": {"sceneType": "icon_text", "text": "Move your savings first", "icon": "piggy_bank"},
}


class TestSceneRendering(unittest.TestCase):
    """Rendering is pure Pillow (no ffmpeg, no network) — safe to unit test
    directly, matching the rest of this suite's "no I/O" convention."""

    def test_every_scene_type_has_sample_coverage(self):
        self.assertEqual(set(_SAMPLE_SCENES), set(RENDERERS))

    def test_all_scene_types_render_without_raising(self):
        for scene_type, data in _SAMPLE_SCENES.items():
            render = RENDERERS[scene_type]
            for t in (0.0, 0.3, 0.7, 1.0):
                with self.subTest(scene_type=scene_type, t=t):
                    frame = render(data, t, theme.DEFAULT_THEME, (1080, 1920))
                    self.assertEqual(frame.size, (1080, 1920))

    def test_renders_at_a_non_vertical_resolution(self):
        frame = RENDERERS["big_number"](_SAMPLE_SCENES["big_number"], 0.5, theme.DEFAULT_THEME, (1920, 1080))
        self.assertEqual(frame.size, (1920, 1080))


class TestResolveSceneFallback(unittest.TestCase):
    def test_invalid_scene_falls_back_to_icon_text_with_block_text(self):
        from engine.motion_graphics.renderer import resolve_scene

        resolved = resolve_scene({"sceneType": "not_a_real_type"}, fallback_text="Put $600 aside immediately.")
        self.assertEqual(resolved["sceneType"], schema.FALLBACK_SCENE_TYPE)
        self.assertIn("$600", resolved["text"])

    def test_valid_scene_passes_through_unchanged(self):
        from engine.motion_graphics.renderer import resolve_scene

        scene = _SAMPLE_SCENES["big_number"]
        self.assertIs(resolve_scene(scene, fallback_text="unused"), scene)

    def test_missing_fallback_text_still_renders_something(self):
        from engine.motion_graphics.renderer import resolve_scene

        resolved = resolve_scene(None, fallback_text="")
        self.assertEqual(resolved["sceneType"], schema.FALLBACK_SCENE_TYPE)
        self.assertTrue(resolved["text"])


class TestIcons(unittest.TestCase):
    def test_unknown_icon_draws_nothing_and_reports_false(self):
        from PIL import Image, ImageDraw

        from engine.motion_graphics import icons

        image = Image.new("RGB", (100, 100), "#000000")
        draw = ImageDraw.Draw(image)
        drawn = icons.draw_icon(draw, "not-a-real-icon", (10, 10, 90, 90), "#FFFFFF")
        self.assertFalse(drawn)
        self.assertEqual(image.getpixel((50, 50)), (0, 0, 0))

    def test_known_icon_draws_and_reports_true(self):
        from PIL import Image, ImageDraw

        from engine.motion_graphics import icons

        image = Image.new("RGB", (100, 100), "#000000")
        draw = ImageDraw.Draw(image)
        self.assertTrue(icons.draw_icon(draw, "check", (10, 10, 90, 90), "#FFFFFF"))


if __name__ == "__main__":
    unittest.main()
