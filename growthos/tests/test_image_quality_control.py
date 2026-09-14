import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import image_quality_control

_QC_ENV_VARS = ("IMAGE_QC_ENABLED", "IMAGE_QC_MODEL", "IMAGE_QC_THRESHOLD_APPROVE", "IMAGE_QC_THRESHOLD_EDIT", "MAX_IMAGE_ATTEMPTS")


def _valid_payload(overall=90, **score_overrides):
    scores = {
        "visualQuality": 90, "characterConsistency": 90, "promptAdherence": 90,
        "composition": 90, "storyRelevance": 90, "technicalQuality": 90,
    }
    scores.update(score_overrides)
    return {"overallScore": overall, "scores": scores, "issues": [], "editInstructions": []}


class TestParseQcResponse(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.pop(name, None) for name in _QC_ENV_VARS}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_valid_payload_high_score_is_approved(self):
        result = image_quality_control.parse_qc_response(_valid_payload(overall=92))
        self.assertIsNotNone(result)
        self.assertTrue(result.approved)
        self.assertEqual(result.recommended_action, "APPROVE")
        self.assertEqual(result.overall_score, 92)

    def test_mid_score_recommends_edit(self):
        result = image_quality_control.parse_qc_response(_valid_payload(overall=75))
        self.assertFalse(result.approved)
        self.assertEqual(result.recommended_action, "EDIT")

    def test_low_score_recommends_regenerate(self):
        result = image_quality_control.parse_qc_response(_valid_payload(overall=40))
        self.assertFalse(result.approved)
        self.assertEqual(result.recommended_action, "REGENERATE")

    def test_thresholds_are_configurable(self):
        os.environ["IMAGE_QC_THRESHOLD_APPROVE"] = "50"
        os.environ["IMAGE_QC_THRESHOLD_EDIT"] = "30"
        result = image_quality_control.parse_qc_response(_valid_payload(overall=55))
        self.assertTrue(result.approved)

    def test_missing_overall_score_falls_back_to_weighted_average(self):
        payload = _valid_payload()
        del payload["overallScore"]
        result = image_quality_control.parse_qc_response(payload)
        self.assertEqual(result.overall_score, 90)

    def test_scores_are_clamped_to_0_100(self):
        result = image_quality_control.parse_qc_response(_valid_payload(visualQuality=150, composition=-20))
        self.assertEqual(result.scores["visualQuality"], 100)
        self.assertEqual(result.scores["composition"], 0)

    def test_not_a_dict_returns_none(self):
        self.assertIsNone(image_quality_control.parse_qc_response("pas un dict"))

    def test_missing_scores_key_returns_none(self):
        self.assertIsNone(image_quality_control.parse_qc_response({"overallScore": 90}))

    def test_incomplete_scores_returns_none(self):
        payload = _valid_payload()
        del payload["scores"]["technicalQuality"]
        self.assertIsNone(image_quality_control.parse_qc_response(payload))

    def test_non_numeric_score_returns_none(self):
        payload = _valid_payload(visualQuality="excellent")
        self.assertIsNone(image_quality_control.parse_qc_response(payload))

    def test_edit_instructions_and_issues_coerced_to_strings(self):
        payload = _valid_payload(overall=75)
        payload["issues"] = ["main déformée", 42]
        payload["editInstructions"] = ["corrige la main droite"]
        result = image_quality_control.parse_qc_response(payload)
        self.assertEqual(result.issues, ["main déformée", "42"])
        self.assertEqual(result.edit_instructions, ["corrige la main droite"])


class TestQcEnabledAndAttempts(unittest.TestCase):
    def setUp(self):
        self._saved = {name: os.environ.pop(name, None) for name in _QC_ENV_VARS}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_disabled_by_default(self):
        self.assertFalse(image_quality_control.qc_enabled())

    def test_enabled_via_env(self):
        os.environ["IMAGE_QC_ENABLED"] = "true"
        self.assertTrue(image_quality_control.qc_enabled())

    def test_evaluate_image_returns_none_when_disabled(self):
        self.assertIsNone(image_quality_control.evaluate_image("does-not-exist.jpg", "un prompt"))

    def test_default_max_attempts_is_3(self):
        self.assertEqual(image_quality_control.max_attempts(), 3)

    def test_max_attempts_configurable_and_floored_at_1(self):
        os.environ["MAX_IMAGE_ATTEMPTS"] = "0"
        self.assertEqual(image_quality_control.max_attempts(), 1)
        os.environ["MAX_IMAGE_ATTEMPTS"] = "5"
        self.assertEqual(image_quality_control.max_attempts(), 5)


if __name__ == "__main__":
    unittest.main()
