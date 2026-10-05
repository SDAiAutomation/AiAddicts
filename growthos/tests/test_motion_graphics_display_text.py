"""Phase 2.8 — display-text contract: viewer-visible content vs production
metadata. Fixtures are the EXACT blocks stored on content item d019a38c
("You Got a Raise… So Why Are You Still Broke?"), where the generator wrote
"Animation: icons pop in—coffee, phone, keys—one after another." into the
viewer field of an `icon_text` scene."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import visuals
from engine.motion_graphics import canvas, display_text, layout, preflight, renderer, schema
from engine.motion_graphics.scenes import RENDERERS
from engine.motion_graphics.theme import resolve_theme

SIZE = (1080, 1920)
THEME = resolve_theme(None)

# --- real production blocks (content item d019a38c, blocks 1 and 4) ---------
REAL_BLOCK_1 = {
    "role": "point",
    "text": "Two things happen immediately, you feel richer, and you start spending on small upgrades right away.",
    "visual": "Medium, hand sliding a phone across a table, then picking up a coffee cup and a car key on the counter.",
    "motion_graphic": {
        "icon": "shopping_cart",
        "text": "Feeling richer leads to small purchases. Animation: icons pop in—coffee, phone, keys—one after another.",
        "sceneType": "icon_text",
    },
}
REAL_BLOCK_4 = {
    "role": "point",
    "text": "This pattern has a name, lifestyle inflation. You raise your lifestyle to match higher income so savings lag behind.",
    "visual": "Wide, apartment interior showing upgraded couch, wardrobe, and new gadgets, camera slowly tracking across the room.",
    "motion_graphic": {
        "icon": "house",
        "text": "Lifestyle inflation: spending rises with income. Animation: income arrow up, spending icons rise to match it.",
        "sceneType": "icon_text",
    },
}

FORBIDDEN = ("animation:", "icons pop", "animate", "camera:", "transition:", "visual:", "pop in", "one after another")


def drawn_strings(render, scene, t=1.0):
    """Every string the scene hands to a text-drawing call."""
    seen: list[str] = []
    real = canvas.draw_text

    def spy(draw, xy, text, *a, **k):
        seen.append(str(text))
        return real(draw, xy, text, *a, **k)

    with mock.patch.object(canvas, "draw_text", spy):
        render(scene, t, THEME, SIZE)
    return seen


def assert_clean(test, strings):
    blob = " ".join(strings).lower()
    for bad in FORBIDDEN:
        test.assertNotIn(bad, blob, strings)


class TestRealProductionBlock(unittest.TestCase):
    def test_animation_instruction_is_never_drawn(self):
        for block in (REAL_BLOCK_1, REAL_BLOCK_4):
            strings = drawn_strings(RENDERERS["icon_text"], block["motion_graphic"])
            assert_clean(self, strings)

    def test_the_financial_message_remains(self):
        shown = " ".join(drawn_strings(RENDERERS["icon_text"], REAL_BLOCK_1["motion_graphic"])).upper()
        self.assertIn("FEELING RICHER LEADS TO SMALL PURCHASES", shown.replace("\n", " "))
        shown4 = " ".join(drawn_strings(RENDERERS["icon_text"], REAL_BLOCK_4["motion_graphic"])).upper()
        self.assertIn("LIFESTYLE INFLATION", shown4)
        self.assertIn("SPENDING RISES WITH INCOME", shown4)

    def test_captions_stay_separate_from_the_motion_text(self):
        # the narration never becomes Motion Graphics text
        shown = " ".join(drawn_strings(RENDERERS["icon_text"], REAL_BLOCK_1["motion_graphic"])).lower()
        self.assertNotIn("two things happen immediately", shown)

    def test_stays_inside_phase_27_safe_bounds(self):
        for block in (REAL_BLOCK_1, REAL_BLOCK_4):
            r = preflight.check_scene(block["motion_graphic"], THEME, SIZE)
            self.assertTrue(r["ok"], r["errors"])
            self.assertGreaterEqual(r["minFontPx"], preflight.MIN_FONT_PX_1920)
            # 1 primary block (<= 2 lines) — not paragraphs above the captions
            with layout.record_boxes() as rec:
                RENDERERS["icon_text"](block["motion_graphic"], 1.0, THEME, SIZE)
            self.assertLessEqual(len(rec), 2)
            self.assertLessEqual(rec[0]["lines"], 2)

    def test_real_fetch_path_hands_the_renderer_a_clean_scene(self):
        captured = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            visuals.motion_graphics, "render_scene_clip", side_effect=lambda scene, *a, **k: captured.append(scene)
        ):
            visuals.fetch_motion_graphics_clips([REAL_BLOCK_1, REAL_BLOCK_4], [6.0, 6.0], "9:16", Path(tmp))
        self.assertEqual(len(captured), 2)
        for scene in captured:
            assert_clean(self, [str(scene.get("text"))])
        self.assertEqual(captured[0]["text"], "Feeling richer leads to small purchases")
        self.assertEqual(captured[0]["icon"], "shopping_cart")  # the icon survives as an icon

    def test_final_frame_differs_from_a_text_dump(self):
        # the rendered pixels really lack the paragraph: the cleaned text is far shorter
        raw = REAL_BLOCK_1["motion_graphic"]["text"]
        clean = display_text.display_text_of(REAL_BLOCK_1["motion_graphic"])
        self.assertLess(len(clean), len(raw) / 2)


class TestStructuredContract(unittest.TestCase):
    STRUCTURED = {
        "sceneType": "icon_text",
        "displayText": "Small purchases add up",
        "icons": ["shopping_cart", "wallet", "coffee"],
        "animation": {"type": "sequential_pop"},
    }

    def test_display_text_is_valid_and_drawn(self):
        self.assertIsNotNone(schema.validate_scene(self.STRUCTURED))
        shown = " ".join(drawn_strings(RENDERERS["icon_text"], self.STRUCTURED)).upper()
        self.assertIn("SMALL PURCHASES ADD UP", shown)

    def test_animation_metadata_never_becomes_text(self):
        strings = drawn_strings(RENDERERS["icon_text"], self.STRUCTURED)
        blob = " ".join(strings).lower()
        for word in ("sequential", "pop", "animation", "coffee"):
            self.assertNotIn(word, blob)

    def test_icon_metadata_is_drawn_not_written(self):
        strings = drawn_strings(RENDERERS["icon_text"], self.STRUCTURED)
        self.assertNotIn("shopping_cart", " ".join(strings))
        self.assertNotIn("wallet", " ".join(strings).lower())
        # two drawable icons are drawn as shapes; the undrawable one ("coffee") is dropped silently
        base = RENDERERS["icon_text"]({"sceneType": "icon_text", "displayText": "X"}, 1.0, THEME, SIZE)
        row = RENDERERS["icon_text"](self.STRUCTURED | {"displayText": "X"}, 1.0, THEME, SIZE)
        self.assertNotEqual(base.tobytes(), row.tobytes())

    def test_display_text_wins_over_legacy_text(self):
        scene = {"sceneType": "icon_text", "displayText": "New line", "text": "Old line. Animation: pop"}
        self.assertEqual(display_text.display_text_of(scene), "New line")

    def test_required_field_still_enforced(self):
        self.assertIsNone(schema.validate_scene({"sceneType": "icon_text"}))
        self.assertIsNone(schema.validate_scene({"sceneType": "icon_text", "displayText": "  "}))


class TestAllSceneTypesIgnoreProductionFields(unittest.TestCase):
    """Audit: all scene types, each with production fields injected next to
    valid viewer content. None of them may reach a text-drawing call."""

    LEAK = "Animation: icons pop in sequentially with camera zoom"
    SAMPLES = {
        "big_number": {"displayValue": "$1,000", "title": "Raise"},
        "money_split": {"title": "Split", "data": [{"label": "Rent", "displayValue": "+$250"}, {"label": "Car", "displayValue": "+$180"}]},
        "progress_bar": {"displayValue": "50%", "targetRatio": 0.5, "label": "Saved"},
        "bar_chart": {"title": "Where", "data": [{"label": "In", "value": 1000, "displayValue": "$1,000"}, {"label": "Out", "value": 850, "displayValue": "$850"}]},
        "donut_chart": {"title": "Mix", "data": [{"label": "A", "value": 60, "displayValue": "60%"}, {"label": "B", "value": 40, "displayValue": "40%"}]},
        "comparison": {"title": "Pick", "optionA": {"label": "Save", "displayValue": "First"}, "optionB": {"label": "Spend", "displayValue": "First"}},
        "before_after": {"title": "Order", "before": {"label": "Before", "displayValue": "Spend"}, "after": {"label": "After", "displayValue": "Save"}},
        "timeline": {"title": "Path", "steps": ["Raise", "Upgrades", "Nothing left"]},
        "compound_growth": {"title": "Growth", "data": [{"label": "Saved", "displayValue": "Grows"}]},
        "checklist": {"title": "Do", "items": ["Automate", "Separate", "Review"]},
        "warning": {"title": "Careful", "label": "Fees"},
        "formula": {"title": "Rule", "terms": ["Income", "- Savings", "= Budget"]},
        "equation_steps": {"title": "Solve", "steps": [
            {"equation": "2x+3=11", "explanation": "Start", "spoken": "private timing"},
            {"equation": "x=4", "explanation": "Answer", "spoken": "private timing"},
        ]},
        "function_graph": {"title": "Line", "slope": 2, "intercept": 3, "highlightX": 1},
        "icon_text": {"text": "Small purchases add up", "icon": "wallet"},
    }

    def test_every_scene_type_is_covered(self):
        self.assertEqual(set(self.SAMPLES), set(schema.SCENE_TYPES))
        self.assertEqual(len(RENDERERS), 15)

    def test_production_fields_never_reach_a_draw_call(self):
        for kind, base in self.SAMPLES.items():
            polluted = dict(base, sceneType=kind, animation={"type": "sequential_pop", "note": self.LEAK},
                            visual=self.LEAK, description=self.LEAK, notes=self.LEAK,
                            instruction=self.LEAK, motion=self.LEAK)
            strings = drawn_strings(RENDERERS[kind], polluted)
            assert_clean(self, strings)
            self.assertTrue(strings, kind)  # and the real content still renders

    def test_leaks_inside_viewer_fields_are_stripped_in_every_list_and_group(self):
        leaky = {
            "sceneType": "checklist", "title": "Do. Animation: pop",
            "items": ["Automate. Animation: fade in", "Separate"],
        }
        assert_clean(self, drawn_strings(RENDERERS["checklist"], leaky))
        leaky = {"sceneType": "comparison", "optionA": {"label": "Save", "displayValue": "First. Camera: zoom"},
                 "optionB": {"label": "Spend", "displayValue": "Visual: arrows"}}
        assert_clean(self, drawn_strings(RENDERERS["comparison"], leaky))


class TestLegacyContaminatedText(unittest.TestCase):
    def test_legacy_text_is_cleaned_by_resolve_scene(self):
        scene = renderer.resolve_scene(REAL_BLOCK_1["motion_graphic"], "unused")
        self.assertEqual(scene["text"], "Feeling richer leads to small purchases")
        self.assertEqual(scene["icon"], "shopping_cart")

    def test_text_that_was_only_a_direction_falls_back_to_the_narration(self):
        raw = {"sceneType": "icon_text", "text": "Animation: icons pop in one after another"}
        fallback = preflight.fallback_text(raw, "Save first. Spend what is left.")  # as visuals.py does
        scene = renderer.resolve_scene(raw, fallback)
        self.assertEqual(scene["text"], "Save first")
        assert_clean(self, drawn_strings(RENDERERS["icon_text"], scene))

    def test_failed_scene_fallback_does_not_resurface_the_direction(self):
        text = preflight.fallback_text(REAL_BLOCK_1["motion_graphic"], "narration")
        assert_clean(self, [text])
        self.assertIn("Feeling richer", text)

    def test_guard_variants(self):
        cases = {
            "Save first. Camera: slow push-in": "Save first.",
            "Save first — Visual: arrow up": "Save first",
            "Save first (animation: pop)": "Save first",
            "Icons pop in one by one. Save more": "Save more",
            "Transition: fade. Scene: office": "",
            "Show: coffee icon": "",
            "Zoom: slow": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(display_text.strip_directions(raw), expected, raw)

    def test_original_dict_is_not_mutated(self):
        raw = dict(REAL_BLOCK_1["motion_graphic"])
        before = dict(raw)
        renderer.resolve_scene(raw, "x")
        display_text.viewer_scene(raw)
        self.assertEqual(raw, before)


class TestOrdinaryWordsSurvive(unittest.TestCase):
    def test_legitimate_copy_is_untouched(self):
        for text in (
            "Show me the money",
            "The scene is set for your raise",
            "Pan out your budget",
            "Cut to the chase",
            "Numbers rise faster than wages",
            "Fade out the old habit and start saving every single month",
            "Camera gear fund: $500",
            "Icons of wealth rarely build wealth",
            "Transition year: save first",
            "Visual spending tracker",
        ):
            self.assertEqual(display_text.strip_directions(text), text, text)
            self.assertFalse(display_text.has_direction_leak(text), text)

    def test_ordinary_words_still_render_in_a_scene(self):
        scene = {"sceneType": "icon_text", "text": "Show me the money", "icon": "money"}
        self.assertIn("SHOW ME THE MONEY", " ".join(drawn_strings(RENDERERS["icon_text"], scene)).upper())

    def test_numbers_and_currency_are_never_altered(self):
        for v in ("$3,000 → $4,000", "+$250", "50%", "$1,000", "×3"):
            self.assertEqual(display_text.viewer_scene({"sceneType": "big_number", "displayValue": v})["displayValue"], v)


class TestDisplayTextBudget(unittest.TestCase):
    NARRATION = ("When people start feeling richer they often begin making lots of small purchases "
                 "that eventually consume their additional income.")

    def test_a_pasted_narration_sentence_is_cut_to_budget(self):
        scene = display_text.viewer_scene({"sceneType": "icon_text", "text": self.NARRATION})
        max_chars, max_words = display_text.BUDGETS["display_text"]
        self.assertLessEqual(len(scene["text"]), max_chars + 1)
        self.assertLessEqual(len(scene["text"].split()), max_words)

    def test_budget_never_lengthens_and_is_idempotent(self):
        once = display_text.viewer_scene({"sceneType": "icon_text", "text": self.NARRATION})
        twice = display_text.viewer_scene(once)
        self.assertEqual(once, twice)

    def test_every_real_stored_string_is_within_budget_untouched(self):
        # every viewer string of the two real stored videos passes unchanged
        real = [
            "Keeps psychological distance from daily money", "Avoid illiquid accounts for your first $1,000",
            "Monthly expenses × 3 = Target emergency fund", "Typical timeline after a raise",
            "Save first, spend leftover", "Check access option", "Common post-raise upgrades",
        ]
        for text in real:
            self.assertEqual(display_text._clean(text, "list_item"), text)

    def test_long_title_and_items_are_bounded(self):
        scene = display_text.viewer_scene({
            "sceneType": "checklist", "title": self.NARRATION, "items": [self.NARRATION],
        })
        self.assertLessEqual(len(scene["title"]), display_text.BUDGETS["title"][0] + 1)
        self.assertLessEqual(len(scene["items"][0]), display_text.BUDGETS["list_item"][0] + 1)

    def test_icon_text_is_at_most_two_lines_for_a_long_line(self):
        with layout.record_boxes() as rec:
            RENDERERS["icon_text"]({"sceneType": "icon_text", "text": self.NARRATION}, 1.0, THEME, SIZE)
        self.assertLessEqual(rec[0]["lines"], 2)


class TestBackwardCompatibility(unittest.TestCase):
    def test_valid_clean_scene_passes_through_by_identity(self):
        scene = {"sceneType": "icon_text", "text": "Save first", "icon": "wallet"}
        self.assertIs(renderer.resolve_scene(scene, "unused"), scene)

    def test_legacy_icon_text_with_text_only_renders(self):
        img = RENDERERS["icon_text"]({"sceneType": "icon_text", "text": "Legacy line"}, 1.0, THEME, SIZE)
        self.assertEqual(img.size, SIZE)

    def test_internal_sync_fields_survive_the_whitelist(self):
        scene = {"sceneType": "checklist", "items": ["A one", "B two"], "_reveals": [0.1, 0.5], "_duration": 6.0}
        out = display_text.viewer_scene(scene)
        self.assertEqual(out["_reveals"], [0.1, 0.5])
        self.assertEqual(out["_duration"], 6.0)

    def test_the_type_alias_for_sceneType_is_kept(self):
        self.assertEqual(display_text.viewer_scene({"type": "warning", "title": "Careful"})["sceneType"], "warning")

    def test_text_field_of_other_scene_types_is_not_invented(self):
        self.assertNotIn("text", display_text.viewer_scene({"sceneType": "big_number", "displayValue": "$1"}))


if __name__ == "__main__":
    unittest.main()
