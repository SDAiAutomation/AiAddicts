import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import explainer_measures as measures  # noqa: E402


def item(**explainer):
    block = {"mode": "templates", "plans": 8, "fallbacks": 1, "cost": 0.5, "costUnknown": False, "renderSeconds": 120.0,
             "totalSeconds": 150.0, "timingSource": "measured", "sfxIncluded": True, "reused": False, **explainer}
    return {"id": "abcdef12-0000", "title": "t", "updated_at": "2026-10-19", "generation_cost_report": {"explainer": block, "totalEstimatedCost": 0.8}}


class MeasuresTests(unittest.TestCase):
    def test_rows_come_only_from_items_with_an_explainer_block(self):
        self.assertIsNone(measures.explainer_row({"id": "x", "generation_cost_report": {"images": {}}}))
        self.assertIsNone(measures.explainer_row({"id": "x", "generation_cost_report": None}))
        self.assertEqual(measures.explainer_row(item())["llmCostUsd"], 0.5)

    def test_unknown_cost_is_not_zero(self):
        row = measures.explainer_row(item(costUnknown=True, cost=0.0))
        self.assertIsNone(row["llmCostUsd"])
        self.assertIn("n/d", measures.render_table([row]))

    def test_means_ignore_reused_renders_and_missing_values(self):
        rows = [measures.explainer_row(item(cost=0.4, renderSeconds=100.0)), measures.explainer_row(item(cost=0.6, renderSeconds=140.0)),
                measures.explainer_row(item(cost=0.0, renderSeconds=None, reused=True)),
                measures.explainer_row(item(timingSource="estimated"))]
        summary = measures.summarize(rows)
        self.assertEqual((summary["videos"], summary["freshRenders"]), (4, 3))
        self.assertEqual(summary["meanLlmCostUsd"], 0.5)
        self.assertEqual(summary["meanRenderSeconds"], 120.0)  # 100, 140 et 120 ; le rendu réutilisé est exclu
        self.assertEqual(summary["estimatedTimings"], 1)
        self.assertIn("4 vidéo(s), dont 3 rendu(s) neuf(s)", measures.render_table(rows))

    def test_empty_means_are_unknown_not_zero(self):
        summary = measures.summarize([])
        self.assertIsNone(summary["meanLlmCostUsd"])
        self.assertEqual(summary["videos"], 0)


if __name__ == "__main__":
    unittest.main()
