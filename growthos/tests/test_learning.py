import unittest

from engine import learning, story_features


def _row(item_id, captured_at, title, hook, archetype=None, hook_type=None, **metrics):
    story = {}
    if archetype:
        story["archetype"] = archetype
    if hook_type:
        story["hookType"] = hook_type
    return {
        "content_item_id": item_id,
        "captured_at": captured_at,
        "content_items": {
            "title": title,
            "story_features": story or None,
            "script": {
                "visual_style": "stock_footage",
                "caption_style": "word_pop",
                "content_goal": "reach",
                "blocks": [{"role": "hook", "text": hook}],
            },
        },
        **metrics,
    }


def _video(item_id, archetype, retention, views=1000, hook_type="mise en situation"):
    return _row(
        item_id, "2026-09-25", f"Titre {item_id}", "Every night the dog came back.",
        archetype=archetype, hook_type=hook_type, views=views, watch_time_pct=retention,
    )


class TestPerformanceLearning(unittest.TestCase):
    def test_performance_score_weights_retention_engagement_and_conversion(self):
        score = learning.performance_score({
            "views": 1000, "watch_time_pct": 50, "likes": 50,
            "comments": 10, "shares": 10, "followers_delta": 10, "leads": 5,
        })
        self.assertEqual(score, 62.5)

    def test_retention_above_100_is_capped(self):
        # Les Shorts regardés en boucle dépassent 100 % de rétention.
        self.assertEqual(
            learning.performance_score({"views": 100, "watch_time_pct": 108}),
            learning.performance_score({"views": 100, "watch_time_pct": 100}),
        )

    def test_hook_fallback_handles_french_and_english(self):
        self.assertEqual(learning.hook_pattern("3 erreurs à éviter"), "liste chiffrée")
        self.assertEqual(learning.hook_pattern("Pourquoi personne ne répond ?"), "question")
        self.assertEqual(learning.hook_pattern("Why did the dog come back?"), "question")
        self.assertEqual(learning.hook_pattern("Never trust a quiet parrot."), "avertissement")
        self.assertEqual(learning.hook_pattern("The octopus escaped every night."), "mise en situation")

    def test_cached_hook_type_wins_over_fallback(self):
        rows = [_video("a", "survie", 60, hook_type="énigme")]
        hooks = [i for i in learning.build_insights(rows) if i["kind"] == "hook"]
        self.assertEqual(hooks[0]["label"], "énigme")

    def test_no_group_per_exact_title(self):
        rows = [_video("a", "survie", 60), _video("b", "survie", 50)]
        kinds = {i["kind"] for i in learning.build_insights(rows)}
        self.assertNotIn("topic", kinds)

    def test_latest_snapshot_merged_with_previous_metrics(self):
        rows = [
            _row("a", "2026-01-01", "A", "Hook", archetype="survie", views=100, watch_time_pct=50),
            _row("a", "2026-01-02", "A", "Hook", archetype="survie", views=200),
        ]
        archetype = next(i for i in learning.build_insights(rows) if i["kind"] == "archetype")
        self.assertEqual(archetype["sample_size"], 1)
        self.assertEqual(archetype["metadata"]["avgRetention"], 50.0)

    def test_videos_without_retention_or_views_are_ignored(self):
        rows = [
            _row("a", "2026-01-01", "A", "Hook", archetype="survie", views=1000),  # pas de rétention
            _video("b", "survie", 60, views=10),  # trop peu de vues
        ]
        self.assertEqual(learning.build_insights(rows), [])

    def test_lift_is_relative_to_account_median(self):
        rows = [
            _video("a", "loyauté inattendue", 80), _video("b", "loyauté inattendue", 70),
            _video("c", "mystère/révélation", 30), _video("d", "mystère/révélation", 20),
            _video("e", "survie", 50),
        ]
        by_label = {i["label"]: i for i in learning.build_insights(rows) if i["kind"] == "archetype"}
        self.assertGreater(by_label["loyauté inattendue"]["metadata"]["lift"], 0)
        self.assertLess(by_label["mystère/révélation"]["metadata"]["lift"], 0)
        self.assertEqual(by_label["survie"]["metadata"]["lift"], 0)


class TestRecommendation(unittest.TestCase):
    def test_no_recommendation_below_minimum_group_size(self):
        rows = [_video("a", "loyauté inattendue", 80), _video("b", "loyauté inattendue", 75),
                _video("c", "survie", 20), _video("d", "survie", 25)]
        self.assertIsNone(learning.build_recommendation(learning.build_insights(rows)))

    def test_recommends_best_and_flags_worst_archetype(self):
        rows = (
            [_video(f"l{i}", "loyauté inattendue", 70 + i) for i in range(3)]
            + [_video(f"m{i}", "mystère/révélation", 20 + i) for i in range(3)]
        )
        reco = learning.build_recommendation(learning.build_insights(rows))
        self.assertIsNotNone(reco)
        self.assertIn("loyauté inattendue", reco["body"])
        self.assertIn("mystère/révélation", reco["body"])
        self.assertIn("ne refais pas", reco["body"])
        self.assertEqual(reco["confidence"], "medium")

    def test_confidence_low_with_few_videos(self):
        rows = [_video(f"l{i}", "survie", 80) for i in range(3)] + [_video("x", "autre", 10), _video("y", "autre", 12)]
        reco = learning.build_recommendation(learning.build_insights(rows))
        self.assertEqual(reco["confidence"], "low")

    def test_empty_insights(self):
        self.assertIsNone(learning.build_recommendation([]))


class TestStoryFeatures(unittest.TestCase):
    def test_parse_keeps_known_values(self):
        parsed = story_features.parse_response({"archetype": "survie", "hookType": "question"})
        self.assertEqual(parsed, {"archetype": "survie", "hookType": "question"})

    def test_parse_maps_unknown_values_to_autre(self):
        parsed = story_features.parse_response({"archetype": "romance", "hookType": "??"})
        self.assertEqual(parsed, {"archetype": "autre", "hookType": "autre"})

    def test_parse_rejects_malformed(self):
        self.assertIsNone(story_features.parse_response([]))
        self.assertIsNone(story_features.parse_response({}))

    def test_quiz_classified_without_network(self):
        result = story_features.classify("Quiz", {"content_format": "quiz"})
        self.assertEqual(result["archetype"], story_features.QUIZ_ARCHETYPE)

    def test_no_model_configured_returns_none(self):
        import os
        saved = os.environ.pop("LEARNING_MODEL", None)
        try:
            self.assertIsNone(story_features.classify("T", {"blocks": []}))
        finally:
            if saved is not None:
                os.environ["LEARNING_MODEL"] = saved


if __name__ == "__main__":
    unittest.main()
