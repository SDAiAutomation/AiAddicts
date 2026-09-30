"""Narration-synced reveals (sync.py) + layout preflight (preflight.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

from engine.motion_graphics import layout, preflight, sync
from engine.motion_graphics.scenes import RENDERERS, _stag
from engine.motion_graphics.theme import resolve_theme

SIZE = (1080, 1920)
THEME = resolve_theme(None)


def words(*pairs):
    return [{"text": t, "start": s, "end": s + 0.3} for t, s in pairs]


CHECKLIST = {"sceneType": "checklist", "title": "Docs", "items": ["Nights booked", "Payment receipts", "Rental contracts"]}
NARRATION = words(("Keep", 0.2), ("nights", 1.0), ("booked", 1.4), ("and", 1.8), ("payment", 3.0), ("receipts", 3.4),
                  ("plus", 4.0), ("rental", 5.0), ("contracts", 5.4))


class TestComputeReveals(unittest.TestCase):
    def test_items_reveal_when_spoken(self):
        r = sync.compute_reveals(CHECKLIST, NARRATION, 7.0)
        self.assertEqual(len(r), 3)
        self.assertAlmostEqual(r[0], (1.0 - sync.LEAD_SECONDS) / 7.0, places=3)
        self.assertAlmostEqual(r[1], (3.0 - sync.LEAD_SECONDS) / 7.0, places=3)
        self.assertAlmostEqual(r[2], (5.0 - sync.LEAD_SECONDS) / 7.0, places=3)

    def test_reveals_are_monotonic_and_bounded(self):
        r = sync.compute_reveals(CHECKLIST, NARRATION, 5.6)
        self.assertEqual(r, sorted(r))
        self.assertLessEqual(max(r), sync.MAX_REVEAL)

    def test_matches_must_follow_narration_order(self):
        scene = {"sceneType": "checklist", "items": ["Rental contracts", "Nights booked"]}
        r = sync.compute_reveals(scene, NARRATION, 7.0)
        self.assertEqual(r, sorted(r))

    def test_unmatched_item_is_interpolated_between_neighbours(self):
        scene = {"sceneType": "checklist", "items": ["Nights booked", "Something unsaid", "Rental contracts"]}
        r = sync.compute_reveals(scene, NARRATION, 7.0)
        self.assertLess(r[0], r[1])
        self.assertLess(r[1], r[2])

    def test_too_few_matches_returns_none(self):
        scene = {"sceneType": "checklist", "items": ["alpha beta", "gamma delta", "epsilon zeta"]}
        self.assertIsNone(sync.compute_reveals(scene, NARRATION, 7.0))

    def test_no_words_or_single_item_or_unsupported_scene(self):
        self.assertIsNone(sync.compute_reveals(CHECKLIST, [], 7.0))
        self.assertIsNone(sync.compute_reveals({"sceneType": "checklist", "items": ["Nights"]}, NARRATION, 7.0))
        self.assertIsNone(sync.compute_reveals({"sceneType": "big_number", "displayValue": "$1"}, NARRATION, 7.0))
        self.assertIsNone(sync.compute_reveals(CHECKLIST, NARRATION, 0))

    def test_prefix_tolerant_matching(self):
        scene = {"sceneType": "timeline", "steps": ["Receipt filed", "Refund issued"]}
        w = words(("receipts", 1.0), ("refunds", 3.0))
        r = sync.compute_reveals(scene, w, 6.0)
        self.assertAlmostEqual(r[1], (3.0 - sync.LEAD_SECONDS) / 6.0, places=3)

    def test_attach_reveals_never_mutates_and_falls_back_to_same_scene(self):
        attached = sync.attach_reveals(CHECKLIST, NARRATION, 7.0)
        self.assertIn("_reveals", attached)
        self.assertNotIn("_reveals", CHECKLIST)
        none_case = sync.attach_reveals({"sceneType": "checklist", "items": ["x y", "z w"]}, NARRATION, 7.0)
        self.assertNotIn("_reveals", none_case)


class TestSceneUsesReveals(unittest.TestCase):
    def test_stag_without_reveals_is_the_original_stagger(self):
        from engine.motion_graphics import animations as anim
        self.assertEqual(_stag({}, 0.4, 1, 3, 0.05, 0.6, 0.35), anim.stagger(0.4, 1, 3, 0.05, 0.6, 0.35))

    def test_item_is_hidden_before_and_visible_after_its_reveal(self):
        data = {"_reveals": [0.1, 0.5, 0.8], "_duration": 7.0}
        self.assertEqual(_stag(data, 0.45, 1, 3), 0.0)
        self.assertEqual(_stag(data, 0.9, 1, 3), 1.0)

    def test_rendered_checklist_differs_before_and_after_the_spoken_moment(self):
        scene = sync.attach_reveals(CHECKLIST, NARRATION, 7.0)
        early = RENDERERS["checklist"](scene, 0.25, THEME, SIZE)
        late = RENDERERS["checklist"](scene, 1.0, THEME, SIZE)
        self.assertNotEqual(list(early.getdata()), list(late.getdata()))


class TestPreflight(unittest.TestCase):
    def test_recorder_is_off_by_default_and_restored(self):
        self.assertIsNone(layout._RECORDER)
        with layout.record_boxes() as rec:
            self.assertIs(layout._RECORDER, rec)
        self.assertIsNone(layout._RECORDER)

    def test_overlapping_text_is_recorded_and_detected(self):
        draw = ImageDraw.Draw(Image.new("RGB", SIZE))
        with layout.record_boxes() as rec:
            layout.draw_fitted(draw, (540, 800), "FIRST LINE OF TEXT", 60, 900, "#fff")
            layout.draw_fitted(draw, (540, 810), "SECOND LINE OF TEXT", 60, 900, "#fff")
        self.assertEqual(len(rec), 2)
        self.assertEqual(layout.find_collisions({"a": rec[0]["box"], "b": rec[1]["box"]}), [("a", "b")])

    def test_old_timeline_geometry_leaves_the_frame(self):
        # first dot at 0.12w, label centred on it with a 410px budget => starts near/below x=0
        draw = ImageDraw.Draw(Image.new("RGB", SIZE))
        with layout.record_boxes() as rec:
            layout.draw_fitted(draw, (130, 900), "QUARTERLY PAYMENT MADE", 46, 410, "#fff", bold=True)
        self.assertLess(rec[0]["box"][0], 0.02 * SIZE[0])

    def test_donut_with_three_rows_shows_all_three_and_stays_out_of_caption_zone(self):
        scene = {"sceneType": "donut_chart", "title": "Budget split", "data": [
            {"label": "Needs", "value": 50, "displayValue": "50%"},
            {"label": "Wants", "value": 30, "displayValue": "30%"},
            {"label": "Savings", "value": 20, "displayValue": "20%"}]}
        result = preflight.check_scene(scene, THEME, SIZE)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["textBoxes"], 4)  # title + 3 legend rows (used to drop the 3rd)

    def test_long_timeline_labels_stay_legible(self):
        for steps in (["Snap photos now", "Save originals to cloud", "Email to your agent"],
                      ["Confirm claim payout", "Talk to agent about gaps", "Set annual review reminder"]):
            r = preflight.check_scene({"sceneType": "timeline", "title": "T", "steps": steps}, THEME, SIZE)
            self.assertTrue(r["ok"], r["errors"])
            self.assertEqual(r["warnings"], [])
            self.assertGreaterEqual(r["minFontPx"], preflight.MIN_FONT_PX_1920)

    def test_all_scene_types_with_realistic_data_pass(self):
        scenes = [
            {"sceneType": "big_number", "title": "Monthly income", "displayValue": "$3,000", "value": 3000,
             "label": "Before any spending", "icon": "wallet"},
            {"sceneType": "money_split", "title": "Where it goes", "displayValue": "$3,000", "value": 3000, "data": [
                {"label": "Rent", "value": 1200, "displayValue": "$1,200"},
                {"label": "Food", "value": 600, "displayValue": "$600"},
                {"label": "Savings", "value": 300, "displayValue": "$300"}]},
            {"sceneType": "progress_bar", "title": "Emergency fund", "displayValue": "65%", "targetRatio": 0.65},
            {"sceneType": "bar_chart", "title": "Spend", "data": [
                {"label": "Jan", "value": 1800, "displayValue": "$1,800"},
                {"label": "Feb", "value": 2100, "displayValue": "$2,100"}]},
            {"sceneType": "comparison", "title": "What would you choose?",
             "optionA": {"label": "Sell now", "displayValue": "Avoid audit risk"},
             "optionB": {"label": "Keep", "displayValue": "Chase refunds"}},
            {"sceneType": "before_after", "title": "After one year",
             "before": {"label": "Before", "displayValue": "$200"}, "after": {"label": "After", "displayValue": "$2,400"}},
            {"sceneType": "compound_growth", "title": "Where it goes", "data": [
                {"label": "Income", "displayValue": "$3,000"}, {"label": "Saved", "displayValue": "$600"}]},
            {"sceneType": "checklist", "title": "Docs", "items": ["Nights booked", "Payment receipts", "Rental contracts"]},
            {"sceneType": "warning", "title": "Possible repayment", "label": "Plus fees"},
            {"sceneType": "formula", "title": "The rule", "terms": ["INCOME", "- SAVINGS", "= SPENDING BUDGET"]},
            {"sceneType": "icon_text", "icon": "bank", "text": "Second-home tax: 0 owed", "label": "Official notice"},
        ]
        for scene in scenes:
            r = preflight.check_scene(scene, THEME, SIZE)
            self.assertTrue(r["ok"], (scene["sceneType"], r["errors"]))


class TestWrapFirst(unittest.TestCase):
    def test_wrap_first_keeps_a_larger_font_than_default_shrink(self):
        draw = ImageDraw.Draw(Image.new("RGB", SIZE))
        text, width = "QUARTERLY PAYMENT MADE", 330
        default = layout.fit_text(draw, text, 46, width, bold=True)
        wrapped = layout.fit_text(draw, text, 46, width, bold=True, wrap_first=True)
        self.assertGreater(wrapped.font.size, default.font.size)
        self.assertLessEqual(wrapped.line_width, width)
        self.assertLessEqual(len(wrapped.lines), 2)

    def test_short_text_is_unchanged_with_wrap_first(self):
        draw = ImageDraw.Draw(Image.new("RGB", SIZE))
        r = layout.fit_text(draw, "KEEP", 46, 400, bold=True, wrap_first=True)
        self.assertEqual((r.font.size, r.lines), (46, ["KEEP"]))


if __name__ == "__main__":
    unittest.main()
