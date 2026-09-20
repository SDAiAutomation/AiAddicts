import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import assembler


def _metrics(**overrides):
    metrics = {
        "voice_characters": 1200,
        "image_reports": [
            {"estimatedCost": 0.05, "usage": {"input_text": 100, "input_image": 0, "output": 1000}},
            {"estimatedCost": 0.07, "usage": {"input_text": 120, "input_image": 0, "output": 1500}},
        ],
    }
    metrics.update(overrides)
    return metrics


class TestGenerationCostReport(unittest.TestCase):
    def test_adds_script_cost_when_usage_and_rates_present(self):
        env = {"ELEVENLABS_USD_PER_1K_CHARS": "0.2", "SCRIPT_PRICE_IN_PER_M": "0.25", "SCRIPT_PRICE_OUT_PER_M": "2"}
        usage = {"model": "gpt-5-mini", "input": 4000, "output": 3000}
        with patch.dict(os.environ, env):
            report = assembler._generation_cost_report(_metrics(script_usage=usage))
        self.assertAlmostEqual(report["script"]["cost"], 0.007)
        self.assertAlmostEqual(report["totalEstimatedCost"], 0.367)
        self.assertEqual(report["missingRates"], [])

    def test_script_rate_missing_is_flagged(self):
        with patch.dict(os.environ, {"ELEVENLABS_USD_PER_1K_CHARS": "0.2"}, clear=True):
            report = assembler._generation_cost_report(_metrics(script_usage={"model": "m", "input": 10, "output": 10}))
        self.assertIn("script", report["missingRates"])

    def test_none_when_nothing_new_was_generated(self):
        self.assertIsNone(assembler._generation_cost_report(None))

    def test_totals_images_and_voice(self):
        with patch.dict(os.environ, {"ELEVENLABS_USD_PER_1K_CHARS": "0.2"}):
            report = assembler._generation_cost_report(_metrics())
        self.assertAlmostEqual(report["images"]["cost"], 0.12)
        self.assertEqual(report["images"]["tokens"], {"input_text": 220, "input_image": 0, "output": 2500})
        self.assertAlmostEqual(report["voice"]["cost"], 0.24)
        self.assertAlmostEqual(report["totalEstimatedCost"], 0.36)
        self.assertEqual(report["missingRates"], [])

    def test_missing_rates_are_flagged_not_guessed(self):
        metrics = _metrics(image_reports=[{"estimatedCost": 0.0, "usage": {"input_text": 1, "input_image": 0, "output": 9}}])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ELEVENLABS_USD_PER_1K_CHARS", None)
            report = assembler._generation_cost_report(metrics)
        self.assertEqual(report["totalEstimatedCost"], 0.0)
        self.assertEqual(sorted(report["missingRates"]), ["images", "voice"])
        self.assertEqual(report["voice"]["characters"], 1200)

    def test_reused_audio_costs_nothing(self):
        report = assembler._generation_cost_report(_metrics(voice_characters=0))
        self.assertEqual(report["voice"], {"characters": 0, "cost": 0.0})
        self.assertNotIn("voice", report["missingRates"])


    def test_over_budget_flag_follows_threshold(self):
        env = {"ELEVENLABS_USD_PER_1K_CHARS": "0.2", "GENERATION_COST_ALERT_USD": "0.30"}
        with patch.dict(os.environ, env):
            self.assertTrue(assembler._generation_cost_report(_metrics())["overBudget"])  # 0,36 > 0,30
        env["GENERATION_COST_ALERT_USD"] = "1.00"
        with patch.dict(os.environ, env):
            self.assertFalse(assembler._generation_cost_report(_metrics())["overBudget"])

    def test_no_threshold_never_flags(self):
        with patch.dict(os.environ, {"ELEVENLABS_USD_PER_1K_CHARS": "0.2"}):
            os.environ.pop("GENERATION_COST_ALERT_USD", None)
            self.assertFalse(assembler._generation_cost_report(_metrics())["overBudget"])


if __name__ == "__main__":
    unittest.main()
