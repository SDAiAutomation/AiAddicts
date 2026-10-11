"""Offline tests: YouTube gross subscriber conversion."""
import unittest
from engine.subscriber_growth import (
    subscribers_gained_per_1000, latest_youtube_snapshots, conversion_insights,
)


def row(id, gained, views=1000, timestamp="2026-10-10T00:00:00Z", **extra):
    return {
        "content_item_id": id, "views": views, "followers_delta": gained,
        "captured_at": timestamp, "platform": "youtube",
        "metric_source": "youtube_auto",
        "content_items": {"story_features": {"archetype": "mystère/révélation"}},
        **extra,
    }


class SubscriberGrowthTests(unittest.TestCase):
    def test_gross_rate_and_missing(self):
        self.assertEqual(subscribers_gained_per_1000(1000, 8), 8.0)
        self.assertIsNone(subscribers_gained_per_1000(1000, -2))
        self.assertIsNone(subscribers_gained_per_1000(0, 1))
        self.assertIsNone(subscribers_gained_per_1000(100, None))
        self.assertIsNone(subscribers_gained_per_1000("bad", 2))

    def test_latest_snapshot_not_double_counted(self):
        old = row("a", 3, timestamp="2026-10-09T00:00:00Z")
        new = row("a", 5, timestamp="2026-10-10T00:00:00Z")
        self.assertEqual(latest_youtube_snapshots([new, old, old]), [new])

    def test_later_missing_does_not_fallback(self):
        old = row("a", 3, timestamp="2026-10-09T00:00:00Z")
        new = row("a", None, timestamp="2026-10-10T00:00:00Z")
        self.assertEqual(conversion_insights([old, new, row("b", 2), row("c", 3)]), [])

    def test_minimum_sample(self):
        rows = [row(str(i), i) for i in (1, 2, 3)]
        result = conversion_insights(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sample_size"], 3)
        self.assertEqual(result[0]["median_subscribers_gained_per_1000_views"], 2.0)

    def test_tiktok_and_unverified_excluded(self):
        rows = [row("a", 1), row("b", 2), row("c", 3)]
        rows[1]["platform"] = "tiktok"
        rows[2]["metric_source"] = "manual"
        self.assertEqual(conversion_insights(rows), [])

    def test_invalid_timestamp_ignored(self):
        self.assertEqual(latest_youtube_snapshots([row("a", 1, timestamp="bad")]), [])


if __name__ == "__main__":
    unittest.main()
