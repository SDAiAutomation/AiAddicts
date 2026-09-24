import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import originality

_ORIGINALITY_ENV_VARS = (
    "ORIGINALITY_CHECK_ENABLED", "ORIGINALITY_MODEL", "ORIGINALITY_HISTORY_LIMIT",
    "ORIGINALITY_THRESHOLD_FLAG", "ORIGINALITY_THRESHOLD_BLOCK", "ORIGINALITY_THRESHOLD_WARN",
    "OPENAI_API_KEY",
)


def _valid_payload(overall=None, **dimension_overrides):
    dims = {
        "name": "concept", "similarity": 40, "matchedVideoIds": ["abc"],
        "explanation": "même idée générale, traitement différent",
    }
    dims.update(dimension_overrides)
    payload = {"dimensions": [dims], "suggestion": None}
    if overall is not None:
        payload["overallSimilarity"] = overall
    return payload


class _EnvTestCase(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.pop(name, None) for name in _ORIGINALITY_ENV_VARS}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class TestParseOriginalityResponse(_EnvTestCase):
    def test_valid_payload_below_threshold_is_not_too_similar(self):
        result = originality.parse_originality_response(_valid_payload(overall=40), compared_count=5, history_available=True)
        self.assertIsNotNone(result)
        self.assertFalse(result.too_similar)
        self.assertEqual(result.overall_similarity, 40)
        self.assertEqual(result.compared_count, 5)
        self.assertTrue(result.history_available)

    def test_high_score_is_too_similar(self):
        result = originality.parse_originality_response(_valid_payload(overall=90), compared_count=5, history_available=True)
        self.assertTrue(result.too_similar)

    def test_legacy_flag_threshold_still_sets_block_level(self):
        os.environ["ORIGINALITY_THRESHOLD_FLAG"] = "30"
        result = originality.parse_originality_response(_valid_payload(overall=35), compared_count=5, history_available=True)
        self.assertTrue(result.too_similar)

    def test_organic_series_range_warns_without_blocking(self):
        # 62-85 = ressemblance mesurée entre vidéos normales d'une même série.
        for score in (70, 85, 89):
            result = originality.parse_originality_response(_valid_payload(overall=score), compared_count=5, history_available=True)
            self.assertFalse(result.too_similar, score)
            self.assertTrue(result.warn, score)

    def test_below_warn_threshold_is_neither(self):
        result = originality.parse_originality_response(_valid_payload(overall=69), compared_count=5, history_available=True)
        self.assertFalse(result.too_similar)
        self.assertFalse(result.warn)

    def test_block_level_also_warns(self):
        result = originality.parse_originality_response(_valid_payload(overall=100), compared_count=5, history_available=True)
        self.assertTrue(result.too_similar)
        self.assertTrue(result.warn)

    def test_new_block_threshold_wins_over_legacy_name(self):
        os.environ["ORIGINALITY_THRESHOLD_FLAG"] = "30"
        os.environ["ORIGINALITY_THRESHOLD_BLOCK"] = "95"
        result = originality.parse_originality_response(_valid_payload(overall=90), compared_count=5, history_available=True)
        self.assertFalse(result.too_similar)

    def test_warn_threshold_never_exceeds_block(self):
        os.environ["ORIGINALITY_THRESHOLD_BLOCK"] = "60"
        os.environ["ORIGINALITY_THRESHOLD_WARN"] = "80"
        self.assertEqual(originality.thresholds(), (60, 60))

    def test_visual_dimension_dropped_when_no_visuals_to_compare(self):
        payload = {
            "dimensions": [
                {"name": "composition visuelle", "similarity": 100, "matchedVideoIds": ["a"]},
                {"name": "concept", "similarity": 50, "matchedVideoIds": ["b"]},
            ],
        }
        result = originality.parse_originality_response(
            payload, compared_count=2, history_available=True, visuals_available=False,
        )
        self.assertEqual([d["name"] for d in result.dimensions], ["concept"])
        self.assertEqual(result.overall_similarity, 50)
        self.assertEqual(result.matched_video_ids, ["b"])

    def test_visual_dimension_kept_when_visuals_exist(self):
        payload = {"dimensions": [{"name": "composition visuelle", "similarity": 80, "matchedVideoIds": []}]}
        result = originality.parse_originality_response(payload, compared_count=2, history_available=True)
        self.assertEqual(len(result.dimensions), 1)

    def test_missing_overall_similarity_falls_back_to_max_dimension(self):
        payload = _valid_payload()
        payload["dimensions"] = [
            {"name": "concept", "similarity": 20, "matchedVideoIds": [], "explanation": ""},
            {"name": "hook", "similarity": 65, "matchedVideoIds": ["v1"], "explanation": "accroche quasi identique"},
        ]
        result = originality.parse_originality_response(payload, compared_count=3, history_available=True)
        self.assertEqual(result.overall_similarity, 65)
        self.assertEqual(result.matched_video_ids, ["v1"])

    def test_empty_dimensions_defaults_to_zero(self):
        result = originality.parse_originality_response({"dimensions": []}, compared_count=3, history_available=True)
        self.assertIsNotNone(result)
        self.assertEqual(result.overall_similarity, 0)
        self.assertFalse(result.too_similar)

    def test_scores_are_clamped_to_0_100(self):
        result = originality.parse_originality_response(_valid_payload(overall=150, similarity=-20), compared_count=1, history_available=True)
        self.assertEqual(result.overall_similarity, 100)
        self.assertEqual(result.dimensions[0]["similarity"], 0)

    def test_not_a_dict_returns_none(self):
        self.assertIsNone(originality.parse_originality_response("pas un dict", compared_count=0, history_available=False))

    def test_missing_dimensions_key_returns_none(self):
        self.assertIsNone(originality.parse_originality_response({}, compared_count=0, history_available=False))

    def test_non_numeric_dimension_similarity_is_skipped(self):
        payload = {"dimensions": [{"name": "concept", "similarity": "haute", "matchedVideoIds": [], "explanation": ""}]}
        result = originality.parse_originality_response(payload, compared_count=1, history_available=True)
        self.assertEqual(result.dimensions, [])

    def test_matched_video_ids_are_deduplicated_and_sorted(self):
        payload = {
            "dimensions": [
                {"name": "concept", "similarity": 80, "matchedVideoIds": ["b", "a"], "explanation": ""},
                {"name": "hook", "similarity": 70, "matchedVideoIds": ["a", "c"], "explanation": ""},
            ],
        }
        result = originality.parse_originality_response(payload, compared_count=2, history_available=True)
        self.assertEqual(result.matched_video_ids, ["a", "b", "c"])

    def test_suggestion_coerced_to_string_or_none(self):
        result = originality.parse_originality_response(_valid_payload(overall=90), compared_count=1, history_available=True)
        self.assertIsNone(result.suggestion)
        payload = _valid_payload(overall=90)
        payload["suggestion"] = "changer d'animal et de décor"
        result = originality.parse_originality_response(payload, compared_count=1, history_available=True)
        self.assertEqual(result.suggestion, "changer d'animal et de décor")


class TestOriginalityEnabledAndCheck(_EnvTestCase):
    def test_disabled_by_default(self):
        self.assertFalse(originality.originality_enabled())

    def test_enabled_via_env(self):
        os.environ["ORIGINALITY_CHECK_ENABLED"] = "true"
        self.assertTrue(originality.originality_enabled())

    def test_check_returns_none_when_disabled(self):
        self.assertIsNone(originality.check_originality({"title": "x", "blocks": []}, [{"id": "1", "script": {}}]))

    def test_check_returns_none_when_model_not_configured(self):
        os.environ["ORIGINALITY_CHECK_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test"
        self.assertIsNone(originality.check_originality({"title": "x", "blocks": []}, [{"id": "1", "script": {}}]))

    def test_empty_history_short_circuits_without_network_call(self):
        os.environ["ORIGINALITY_CHECK_ENABLED"] = "true"
        os.environ["ORIGINALITY_MODEL"] = "gpt-test"
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with patch("engine.originality.requests.post") as mock_post:
            result = originality.check_originality({"title": "x", "blocks": []}, [])
            mock_post.assert_not_called()
        self.assertIsNotNone(result)
        self.assertFalse(result.history_available)
        self.assertEqual(result.compared_count, 0)
        self.assertFalse(result.too_similar)


class TestBuildMessages(unittest.TestCase):
    def test_truncates_long_block_text_and_includes_past_ids(self):
        long_text = "a" * 2000
        script = {"title": "t", "blocks": [{"role": "hook", "text": long_text, "visual": ""}]}
        history = [{"id": "past-1", "created_at": "2026-01-01", "script": {"title": "p", "blocks": []}}]
        messages = originality._build_messages(script, history)
        user_content = messages[1]["content"]
        self.assertIn("past-1", user_content)
        self.assertLessEqual(len(user_content), 2000 + 5000)  # borné, pas illimité


if __name__ == "__main__":
    unittest.main()
