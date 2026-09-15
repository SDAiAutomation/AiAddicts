import unittest

from engine import learning


def _row(item_id, captured_at, title, hook, **metrics):
    return {
        "content_item_id": item_id,
        "captured_at": captured_at,
        "content_items": {
            "title": title,
            "script": {
                "visual_style": "stock_footage",
                "caption_style": "word_pop",
                "content_goal": "reach",
                "blocks": [{"role": "hook", "text": hook}],
            },
        },
        **metrics,
    }


class TestPerformanceLearning(unittest.TestCase):
    def test_performance_score_weights_retention_engagement_and_conversion(self):
        score = learning.performance_score({
            "views": 1000, "watch_time_pct": 50, "likes": 50,
            "comments": 10, "shares": 10, "followers_delta": 10, "leads": 5,
        })
        self.assertEqual(score, 62.5)

    def test_hook_patterns_are_reusable(self):
        self.assertEqual(learning.hook_pattern("3 erreurs à éviter"), "liste chiffrée")
        self.assertEqual(learning.hook_pattern("Pourquoi personne ne répond ?"), "question")
        self.assertEqual(learning.hook_pattern("Cette erreur détruit tout"), "avertissement")

    def test_build_insights_keeps_latest_snapshot_and_aggregates_format(self):
        rows = [
            _row("a", "2026-01-01", "Sujet A", "3 erreurs", views=100, watch_time_pct=10),
            _row("a", "2026-01-02", "Sujet A", "3 erreurs", views=100, watch_time_pct=50),
            _row("b", "2026-01-02", "Sujet B", "5 secrets", views=100, watch_time_pct=70),
        ]
        insights = learning.build_insights(rows)
        formats = [item for item in insights if item["kind"] == "format"]
        list_hooks = [item for item in insights if item["kind"] == "hook"]
        self.assertEqual(formats[0]["sample_size"], 2)
        self.assertEqual(list_hooks[0]["sample_size"], 2)
        self.assertEqual(len(list_hooks[0]["metadata"]["examples"]), 2)

    def test_partial_latest_snapshot_keeps_previous_metrics(self):
        rows = [
            _row("a", "2026-01-01", "Sujet A", "3 erreurs", views=100, watch_time_pct=50),
            _row("a", "2026-01-02", "Sujet A", "3 erreurs", views=200),
        ]
        topic = next(item for item in learning.build_insights(rows) if item["kind"] == "topic")
        self.assertEqual(topic["performance_score"], 30.0)

    def test_recommendation_confidence_uses_number_of_videos(self):
        insights = [
            {"kind": "hook", "label": "question", "performance_score": 80, "sample_size": 6},
            {"kind": "topic", "label": "Sujet", "performance_score": 70, "sample_size": 6},
            {"kind": "format", "label": "stock", "performance_score": 60, "sample_size": 6},
        ]
        recommendation = learning.build_recommendation(insights)
        self.assertEqual(recommendation["confidence"], "medium")
        self.assertIn("question", recommendation["body"])


if __name__ == "__main__":
    unittest.main()
