import base64
import copy
import hashlib
import hmac
import json
import os
import unittest
from unittest.mock import patch

from engine import learning, recommendation_tracking as tracking, story_features


KEY = "test-only-recommendation-key"


def token_for(receipt):
    payload = base64.urlsafe_b64encode(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(hmac.new(KEY.encode(), (tracking.PURPOSE + payload).encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return payload + "." + signature


def fixture():
    script = {"title": "La clé", "blocks": [{"role": "hook", "text": "Pourquoi cette clé ?", "visual": "Une clé dorée."}]}
    receipt = {
        "version": 1, "account_id": "account", "organization_id": "org", "generation_id": "generation",
        "generated_at": "2026-09-26T09:00:00Z", "script_fingerprint": tracking.script_fingerprint(script),
        "recommendation": {"id": "recommendation", "generated_at": "2026-09-25T09:00:00Z", "body": "Tester une question",
                           "experiment": {"version": 1, "hypothesis": "Une question pour ouvrir une nouvelle histoire",
                                          "target": {"kind": "hook", "label": "question", "direction": "favor"},
                                          "baseline": {"metric": "watch_time_pct", "value": 40, "sample_size": 3,
                                                       "minimum_views": 50, "sources": [{"content_item_id": "old"}]}}},
    }
    script["recommendation_receipt"] = token_for(receipt)
    item = {"id": "video", "account_id": "account", "script": script, "story_features": {
        "version": story_features.VERSION, "input_fingerprint": tracking.script_fingerprint(script), "hookType": "question",
    }}
    rows = [{"content_item_id": "video", "captured_at": "2026-09-27T09:00:00Z", "views": 100,
             "watch_time_pct": 60, "content_items": {"account_id": "account"}}]
    return item, receipt, rows


@patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": KEY})
class TestRecommendationTracking(unittest.TestCase):
    def test_signed_snapshot_and_descriptive_outcome(self):
        item, receipt, rows = fixture()
        report = tracking.build_report(item, rows)
        self.assertFalse(report["causal"])
        self.assertEqual(report["application"]["status"], "consistent")
        self.assertEqual(report["outcome"]["difference_points"], 20)
        self.assertEqual(report["recommendation_id"], "recommendation")
        receipt["recommendation"]["body"] = "Modified after generation"
        self.assertEqual(tracking.read_receipt(item["script"]["recommendation_receipt"], "account")["recommendation"]["body"], "Tester une question")

    def test_forged_and_foreign_receipts_are_not_attributed(self):
        item, _, rows = fixture()
        valid = item["script"]["recommendation_receipt"]
        self.assertIsNone(tracking.read_receipt(valid, "another-account"))
        item["script"]["recommendation_receipt"] = valid[:-10] + "tampered00"
        self.assertEqual(tracking.build_report(item, rows)["application"]["reason"], "invalid_receipt")

    def test_no_receipt_does_not_invent_a_test(self):
        self.assertIsNone(tracking.build_report({"id": "old", "account_id": "a", "script": {}}, []))

    def test_no_measurement_and_zero_are_distinct(self):
        item, _, rows = fixture()
        self.assertEqual(tracking.build_report(item, [])["outcome"]["status"], "awaiting_metrics")
        rows[0]["watch_time_pct"] = None
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "missing_metrics")
        rows[0]["watch_time_pct"] = 0
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["difference_points"], -40)

    def test_views_only_snapshot_does_not_reuse_old_retention(self):
        item, _, rows = fixture()
        rows.append({**rows[0], "captured_at": "2026-09-28T09:00:00Z", "views": 400, "watch_time_pct": None})
        report = tracking.build_report(item, rows)
        self.assertEqual(report["outcome"]["status"], "missing_metrics")
        self.assertIsNone(report["outcome"]["retention"])

    def test_insufficient_views_and_other_accounts(self):
        item, _, rows = fixture()
        rows[0]["views"] = 49
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "insufficient_views")
        rows[0]["content_items"]["account_id"] = "foreign"
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "awaiting_metrics")

    def test_stale_classification_after_edit_requires_review(self):
        item, _, rows = fixture()
        item["script"]["blocks"][0]["text"] = "La porte reste ouverte."
        report = tracking.build_report(item, rows)
        self.assertTrue(report["edited_since_generation"])
        self.assertEqual(report["application"]["status"], "needs_review")

    def test_contradictory_feature_is_not_reported_as_applied(self):
        item, _, rows = fixture()
        item["story_features"]["hookType"] = "mise en situation"
        self.assertEqual(tracking.build_report(item, rows)["application"]["status"], "not_observed")

    def test_cannot_compare_to_itself_or_old_generation(self):
        item, receipt, rows = fixture()
        receipt["recommendation"]["experiment"]["baseline"]["sources"][0]["content_item_id"] = "video"
        item["script"]["recommendation_receipt"] = token_for(receipt)
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "baseline_overlap")
        rows[0]["captured_at"] = "2026-09-25T09:00:00Z"
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "predates_generation")

    def test_old_render_metrics_are_not_assigned_to_new_script(self):
        item, _, rows = fixture()
        item.update({"script_version": 2, "video_script_version": 1})
        self.assertEqual(tracking.build_report(item, rows)["outcome"]["status"], "script_changed_since_render")

    def test_format_and_avoid_are_checked_without_model(self):
        experiment = {"version": 1, "target": {"kind": "format", "label": "standard · default · bold_stroke", "direction": "avoid"}}
        self.assertEqual(tracking.assess_application({}, experiment, None)["status"], "not_observed")
        self.assertEqual(tracking.assess_application({"visual_style": "anime"}, experiment, None)["status"], "consistent")

    def test_legacy_recommendation_is_explicitly_unverified(self):
        item, receipt, rows = fixture()
        receipt["recommendation"].pop("experiment")
        item["script"]["recommendation_receipt"] = token_for(receipt)
        report = tracking.build_report(item, rows)
        self.assertEqual(report["application"]["reason"], "unstructured_recommendation")
        self.assertEqual(report["outcome"]["status"], "baseline_unavailable")

    def test_nonfinite_measurements_stay_unknown(self):
        item, _, rows = fixture()
        rows[0]["watch_time_pct"] = "NaN"
        self.assertIsNone(tracking.build_report(item, rows)["outcome"]["retention"])

    def test_fingerprint_fixture_is_shared_with_typescript(self):
        item, _, _ = fixture()
        expected = hashlib.sha256('["La clé","standard","hook","Pourquoi cette clé ?","Une clé dorée."]'.encode()).hexdigest()
        self.assertEqual(tracking.script_fingerprint(item["script"]), expected)


class TestExperimentBaseline(unittest.TestCase):
    def test_complete_historical_snapshots_and_one_primary_target(self):
        rows = [{"content_item_id": str(i), "captured_at": "2026-09-20T00:00:00Z", "views": 100,
                 "watch_time_pct": 80 if i < 3 else 20,
                 "content_items": {"script": {}, "story_features": {"archetype": "survie" if i < 3 else "aventure"}}}
                for i in range(6)]
        rows.append({**copy.deepcopy(rows[0]), "captured_at": "2026-09-21T00:00:00Z", "views": 500, "watch_time_pct": None})
        recommendation = learning.build_recommendation(learning.build_insights(rows))
        experiment = recommendation["experiment"]
        self.assertEqual(experiment["baseline"]["sample_size"], 6)
        self.assertEqual(experiment["baseline"]["value"], 50)
        self.assertEqual(experiment["baseline"]["window_end"], "2026-09-20T00:00:00Z")
        self.assertIn(experiment["target"]["kind"], ("archetype", "hook", "format"))
        self.assertEqual(len(experiment["baseline"]["sources"]), 6)


if __name__ == "__main__":
    unittest.main()
