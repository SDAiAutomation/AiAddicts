import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import explainer_effort_sweep as sweep  # noqa: E402


class EffortSweepTests(unittest.TestCase):
    def test_default_is_read_only_and_announces_budget(self):
        output = io.StringIO()
        with patch.object(sweep, "run_sweep") as run, redirect_stdout(output):
            self.assertEqual(sweep.main([]), 0)
        run.assert_not_called()
        self.assertIn("2.40 $", output.getvalue())
        self.assertIn("Aucun appel effectué", output.getvalue())

    def test_composer_cost_stays_unknown_if_any_call_is_unpriced(self):
        report = {"spend": {"calls": [{"step": "director", "costUsd": 0.5},
                                      {"step": "composer#1", "costUsd": 0.2},
                                      {"step": "composer#2", "costUsd": None}]}}
        self.assertIsNone(sweep.composer_cost(report))
        self.assertEqual(sweep.composer_cost({"spend": {"calls": []}}), None)

    def test_non_finite_budget_is_rejected_before_api_call(self):
        for value in ("nan", "inf", "-inf", "0"):
            with self.subTest(value=value), patch.object(sweep, "run_sweep") as run, redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                sweep.main(["--execute", "--budget-usd", value])
            run.assert_not_called()

    def test_comparison_shows_both_efforts_and_fallbacks(self):
        rows = [{"effort": "low", "composerCostUsd": 0.1, "totalCostUsd": 0.3,
                 "fallbackPlans": ["p2"], "video": "low.mp4"},
                {"effort": "medium", "composerCostUsd": None, "totalCostUsd": None,
                 "fallbackPlans": [], "video": "medium.mp4"}]
        table = sweep.comparison(rows)
        self.assertIn("| low | 0.1 | 0.3 | p2 |", table)
        self.assertIn("| medium | n/d | n/d | aucun |", table)


if __name__ == "__main__":
    unittest.main()
