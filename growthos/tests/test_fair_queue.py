import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import repo


def _row(item_id, organization):
    return {"id": item_id, "script": {"title": item_id}, "accounts": {"organization_id": organization}}


class TestPickFairItem(unittest.TestCase):
    def test_single_organization_keeps_arrival_order(self):
        queued = [_row("a1", "A"), _row("a2", "A"), _row("a3", "A")]
        self.assertEqual(repo.pick_fair_item(queued, ["A", "A"])["id"], "a1")

    def test_one_organization_flooding_the_queue_does_not_starve_the_other(self):
        queued = [_row(f"a{i}", "A") for i in range(1, 6)] + [_row("b1", "B")]
        # A vient d'être servie : B passe devant les cinq vidéos de A.
        self.assertEqual(repo.pick_fair_item(queued, ["A", "A", "B"])["id"], "b1")

    def test_never_served_organization_goes_first(self):
        queued = [_row("a1", "A"), _row("b1", "B")]
        self.assertEqual(repo.pick_fair_item(queued, ["A"])["id"], "b1")

    def test_least_recently_served_organization_wins(self):
        queued = [_row("a1", "A"), _row("b1", "B"), _row("c1", "C")]
        # Plus récent d'abord : C, puis B, puis A -> A est la moins récemment servie.
        self.assertEqual(repo.pick_fair_item(queued, ["C", "B", "A"])["id"], "a1")
        self.assertEqual(repo.pick_fair_item(queued, ["A", "C", "B"])["id"], "b1")

    def test_tie_keeps_the_oldest_item(self):
        queued = [_row("a1", "A"), _row("b1", "B")]
        self.assertEqual(repo.pick_fair_item(queued, [])["id"], "a1")

    def test_within_an_organization_the_oldest_item_is_taken(self):
        queued = [_row("a1", "A"), _row("b1", "B"), _row("b2", "B")]
        self.assertEqual(repo.pick_fair_item(queued, ["A"])["id"], "b1")


class _Query:
    def __init__(self, client, table):
        self.client, self.table, self.filters, self.payload = client, table, {}, None

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.client.calls.append((self.table, self.payload, dict(self.filters)))
        if self.table == "product_events":
            if self.client.fail_events:
                raise RuntimeError("table indisponible")
            return type("R", (), {"data": self.client.events})()
        if self.payload is not None:
            return type("R", (), {"data": [{"id": self.filters["id"]}] if self.client.claim_succeeds else []})()
        return type("R", (), {"data": self.client.queued})()


class _FakeClient:
    def __init__(self, queued, events=(), fail_events=False, claim_succeeds=True):
        self.queued, self.events = queued, [{"organization_id": o} for o in events]
        self.fail_events, self.claim_succeeds, self.calls = fail_events, claim_succeeds, []

    def table(self, name):
        return _Query(self, name)


class TestClaimQueuedItem(unittest.TestCase):
    def setUp(self):
        self._original = repo.reclaim_stale_generating_items
        repo.reclaim_stale_generating_items = lambda client: 0

    def tearDown(self):
        repo.reclaim_stale_generating_items = self._original

    def _claimed_id(self, client):
        item = repo.claim_queued_item(client)
        return item and item["id"]

    def test_solo_tenant_path_makes_no_extra_query(self):
        client = _FakeClient([_row("a1", "A"), _row("a2", "A")])
        self.assertEqual(self._claimed_id(client), "a1")
        self.assertNotIn("product_events", [call[0] for call in client.calls])

    def test_two_organizations_alternate(self):
        client = _FakeClient([_row("a1", "A"), _row("a2", "A"), _row("b1", "B")], events=["A"])
        self.assertEqual(self._claimed_id(client), "b1")
        self.assertEqual([c for c in client.calls if c[1]][0][2]["id"], "b1")

    def test_fairness_failure_falls_back_to_arrival_order(self):
        client = _FakeClient([_row("a1", "A"), _row("b1", "B")], fail_events=True)
        self.assertEqual(self._claimed_id(client), "a1")

    def test_empty_queue_and_lost_race_return_none(self):
        self.assertIsNone(repo.claim_queued_item(_FakeClient([])))
        self.assertIsNone(repo.claim_queued_item(_FakeClient([_row("a1", "A")], claim_succeeds=False)))

    def test_claimed_item_keeps_its_historical_shape(self):
        item = repo.claim_queued_item(_FakeClient([_row("a1", "A")]))
        self.assertEqual(set(item), {"id", "script"})


if __name__ == "__main__":
    unittest.main()
