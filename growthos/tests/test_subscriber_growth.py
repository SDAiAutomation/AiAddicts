"""Offline tests for isolated subscriber analytics."""
import unittest

from engine.subscriber_growth import subscribers_per_1000, conversion_insights


class SubscriberGrowthTests(unittest.TestCase):
    def test_rate(self):
        self.assertEqual(subscribers_per_1000(1000, 8), 8.0)
        self.assertEqual(subscribers_per_1000(1000, -2), -2.0)
        self.assertIsNone(subscribers_per_1000(0, 1))
        self.assertIsNone(subscribers_per_1000(100, None))
        self.assertIsNone(subscribers_per_1000("invalid", 2))

    def test_minimum_sample_and_missing_data(self):
        rows = [
            {"content_item_id": str(i), "views": 1000, "followers_delta": i,
             "content_items": {"story_features": {"archetype": "mystère/révélation"}}}
            for i in (1, 2, 3)
        ]
        rows.append({"content_item_id": "4", "views": 1000, "followers_delta": None,
                     "content_items": {"story_features": {"archetype": "mystère/révélation"}}})
        result = conversion_insights(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sample_size"], 3)
        self.assertEqual(result[0]["median_net_subscribers_per_1000_views"], 2.0)

    def test_duplicate_video_is_not_double_counted(self):
        row = {"content_item_id": "a", "views": 100, "followers_delta": 1,
               "content_items": {"story_features": {"hookType": "question"}}}
        self.assertEqual(conversion_insights([row, row, row]), [])


if __name__ == "__main__":
    unittest.main()
