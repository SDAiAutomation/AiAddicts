import unittest
from unittest import mock

from growthos.engine.story_animation import claim


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.patch = db, name, {}, None

    def select(self, *_):
        return self

    def update(self, patch):
        self.patch = patch
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        rows = [r for r in self.db.rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.patch is None:
            return FakeResult(list(rows))
        if self.db.lose_race:
            return FakeResult([])
        for r in rows:
            r.update(self.patch)
        return FakeResult(rows)


class FakeClient:
    def __init__(self, rows, lose_race=False):
        self.rows, self.lose_race = rows, lose_race

    def table(self, name):
        assert name == "content_items"
        return FakeTable(self, name)


def row(i, status="queued", version=None, fmt="story"):
    script = {"content_format": fmt, "story": {"version": version}} if version is not None else {"content_format": fmt}
    return {"id": i, "status": status, "script": script}


class ClaimTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("growthos.engine.story_animation.claim.repo.reclaim_stale_generating_items", return_value=0)
        self.reclaim = patcher.start()
        self.addCleanup(patcher.stop)

    def test_takes_the_oldest_animated_item_and_marks_it_generating(self):
        client = FakeClient([row("std"), row("old", version=2), row("new", version=2)])
        item = claim.claim_animated_item(client)
        self.assertEqual(item["id"], "old")
        self.assertEqual([r["status"] for r in client.rows], ["queued", "generating", "queued"])

    def test_never_touches_other_formats(self):
        client = FakeClient([row("std"), row("quiz", fmt="quiz"), row("v1", version=1)])
        self.assertIsNone(claim.claim_animated_item(client))
        self.assertTrue(all(r["status"] == "queued" for r in client.rows))

    def test_empty_queue(self):
        self.assertIsNone(claim.claim_animated_item(FakeClient([])))

    def test_losing_the_race_returns_nothing(self):
        client = FakeClient([row("a", version=2)], lose_race=True)
        self.assertIsNone(claim.claim_animated_item(client))
        self.assertEqual(client.rows[0]["status"], "queued")

    def test_already_generating_items_are_not_claimed(self):
        client = FakeClient([row("a", status="generating", version=2)])
        self.assertIsNone(claim.claim_animated_item(client))

    def test_orphans_are_reclaimed_first(self):
        claim.claim_animated_item(FakeClient([]))
        self.reclaim.assert_called_once()


if __name__ == "__main__":
    unittest.main()
