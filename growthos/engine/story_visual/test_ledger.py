"""Cumulative, durable episode ceiling: retries, regenerations, timeouts, unreadable state and concurrent workers.
Deterministic: stub providers and an in-memory stand-in for `content_assets` that enforces the real table's unique constraint."""
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from growthos.engine.story_visual import cost, ledger, orchestrator, pipeline, sample


class UniqueViolation(Exception):
    code = "23505"


class FakeTable:
    """The slice of `content_assets` the ledger uses, with `unique (content_item_id, kind, input_hash)` and a lock (atomic insert)."""

    def __init__(self, store):
        self.store, self.op, self.filters, self.values = store, None, {}, None
        self.pattern = None

    def select(self, *_):
        self.op = "select"
        return self

    def insert(self, values):
        self.op, self.values = "insert", values
        return self

    def update(self, values):
        self.op, self.values = "update", values
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def like(self, column, pattern):
        self.pattern = (column, pattern.rstrip("%"))
        return self

    def execute(self):
        return self.store.run(self)


class FakeDb:
    def __init__(self):
        self.rows, self.lock, self.read_error, self.write_error = [], threading.Lock(), None, None
        self.before_insert = None  # hook(db): lets a test slip a competing row in between a worker's read and its insert
        self.table_name = None

    def table(self, name):
        assert name == "content_assets"
        return FakeTable(self)

    def run(self, q):
        with self.lock:
            matching = [r for r in self.rows if all(r.get(k) == v for k, v in q.filters.items())
                        and (q.pattern is None or str(r.get(q.pattern[0], "")).startswith(q.pattern[1]))]
            if q.op == "select":
                if self.read_error:
                    raise self.read_error
                return type("R", (), {"data": [dict(r) for r in matching]})()
            if q.op == "insert":
                if self.write_error:
                    raise self.write_error
                hook, self.before_insert = self.before_insert, None
                if hook:
                    hook(self)
                key = (q.values["content_item_id"], q.values["kind"], q.values["input_hash"])
                if any((r["content_item_id"], r["kind"], r["input_hash"]) == key for r in self.rows):
                    raise UniqueViolation("duplicate key value violates unique constraint (23505)")
                self.rows.append(dict(q.values))
                return type("R", (), {"data": [dict(q.values)]})()
            for r in matching:
                r.update(q.values)
            return type("R", (), {"data": [dict(r) for r in matching]})()


ITEM = "11111111-2222-4333-8444-555555555555"


def make(db, cap=0.30, item=ITEM):
    return ledger.DurableLedger(db, item, cap)


def plan():
    p = sample.moral_plan()
    p["voice_id"] = "VoiceId12345"
    return p


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = FakeDb()

    def run_images(self, provider, work, cap=0.30, unit=0.05, only=None, force=None):
        tracker = cost.BudgetTracker(cost.Budget(max_usd=10), ledger=make(self.db, cap))  # per-run budget is NOT the limit here
        return orchestrator.generate_scene_images(plan(), tenant_id="t1", work_dir=work, provider=provider, tracker=tracker, expected_unit_usd=unit,
                                                  only=only, force=force), tracker


class CountingMeasured(sample.PlaceholderImageProvider):
    """Works and reports a measured cost per image."""

    def __init__(self, usd):
        super().__init__()
        self.usd = usd

    def __call__(self, prompt, out_path, **kw):
        result = super().__call__(prompt, out_path, **kw)
        return orchestrator.ImageResult(result.path, self.usd, result.usage)


class TestCumulativeCeiling(Tmp):
    def test_retries_on_a_fresh_runner_cannot_exceed_the_ceiling(self):
        first = CountingMeasured(0.05)
        self.run_images(first, self.tmp / "run1", only={"s1", "s2", "s3"})
        self.assertEqual((len(first.calls), make(self.db).total()), (3, 0.15))
        second = CountingMeasured(0.05)  # ephemeral runner: no manifest, no cache, only the durable ledger remains
        with self.assertRaises(cost.BudgetExceeded):
            self.run_images(second, self.tmp / "run2")  # needs 8 images: only 3 more fit under 0.30 cumulative
        self.assertEqual(len(second.calls), 3)
        self.assertEqual(make(self.db).total(), 0.30)

    def test_regeneration_counts_against_the_same_ceiling(self):
        provider = CountingMeasured(0.05)
        self.run_images(provider, self.tmp / "w", cap=0.30, only={"s1", "s2", "s3", "s4", "s5"})
        self.assertEqual(make(self.db).total(), 0.25)
        self.run_images(provider, self.tmp / "w", cap=0.30, only={"s1"}, force={"s1"})  # 0.30: allowed
        with self.assertRaises(cost.BudgetExceeded):
            self.run_images(provider, self.tmp / "w", cap=0.30, only={"s2"}, force={"s2"})  # would be 0.35
        self.assertEqual(len(provider.calls), 6)

    def test_a_measured_cost_below_the_reservation_releases_the_difference(self):
        self.run_images(CountingMeasured(0.01), self.tmp / "w", unit=0.05, only={"s1", "s2"})
        self.assertEqual(make(self.db).total(), 0.02)

    def test_exhausted_before_any_call_refuses_the_call(self):
        led = make(self.db, cap=0.10)
        led.reserve("image:s1", 0.10)
        provider = CountingMeasured(0.05)
        with self.assertRaises(cost.BudgetExceeded):
            self.run_images(provider, self.tmp / "w", cap=0.10)
        self.assertEqual(provider.calls, [])

    def test_unknown_or_invalid_amounts_are_refused(self):
        led = make(self.db)
        for bad in (None, float("nan"), float("inf"), -1, True, "0.05"):
            with self.subTest(bad=bad), self.assertRaises(cost.BudgetExceeded):
                led.reserve("image:s1", bad)
        self.assertEqual(self.db.rows, [])


class TestTimeoutsAndUncertainResults(Tmp):
    def test_a_provider_timeout_is_never_counted_as_free(self):
        class Timeout(sample.PlaceholderImageProvider):
            def __call__(self, *a, **k):
                self.calls.append("x")
                raise TimeoutError("read timed out")
        provider = Timeout()
        manifest, tracker = self.run_images(provider, self.tmp / "w", cap=0.10)
        self.assertEqual(len(provider.calls), 1)  # fail fast: the episode stops at the first failing scene
        self.assertEqual(manifest["s1"]["status"], "failed")
        self.assertEqual(make(self.db).total(), 0.05)  # the reservation stays: the call may have been billed
        self.assertEqual(tracker.total, 0.05)
        self.assertEqual(tracker.kinds["image:s1"], cost.UNPRICED)
        self.assertTrue(any("uncertain" in r["provider"] for r in self.db.rows))

    def test_uncertain_calls_accumulate_across_runs_until_the_ceiling_stops_them(self):
        class Timeout(sample.PlaceholderImageProvider):
            def __call__(self, *a, **k):
                self.calls.append("x")
                raise TimeoutError("read timed out")
        calls = 0
        for attempt in range(5):
            provider = Timeout()
            try:
                self.run_images(provider, self.tmp / f"run{attempt}", cap=0.10)
            except cost.BudgetExceeded:
                pass
            calls += len(provider.calls)
        self.assertEqual(calls, 2)  # 0.05 + 0.05 = the 0.10 ceiling: no third paid attempt, although none of them ever succeeded
        self.assertEqual(make(self.db, cap=0.10).total(), 0.10)

    def test_a_successful_call_with_an_unknown_cost_keeps_the_reservation(self):
        class Unpriced(sample.PlaceholderImageProvider):
            def __call__(self, prompt, out_path, **kw):
                result = super().__call__(prompt, out_path, **kw)
                return orchestrator.ImageResult(result.path, None, result.usage)
        self.run_images(Unpriced(), self.tmp / "w", only={"s1"})
        self.assertEqual(make(self.db).total(), 0.05)


class TestFailClosed(Tmp):
    def test_an_unreadable_ledger_refuses_the_paid_call(self):
        self.db.read_error = ConnectionError("db down")
        provider = CountingMeasured(0.05)
        with self.assertRaises(ledger.LedgerUnavailable):
            self.run_images(provider, self.tmp / "w")
        self.assertEqual(provider.calls, [])

    def test_a_ledger_that_cannot_be_written_refuses_the_paid_call(self):
        self.db.write_error = ConnectionError("db down")
        provider = CountingMeasured(0.05)
        with self.assertRaises(ledger.LedgerUnavailable):
            self.run_images(provider, self.tmp / "w")
        self.assertEqual(provider.calls, [])

    def test_corrupted_rows_refuse(self):
        self.db.rows.append({"content_item_id": ITEM, "kind": "image", "input_hash": ledger.LEDGER_PREFIX + "000001", "estimated_cost": None, "provider": "x"})
        with self.assertRaises(ledger.LedgerUnavailable):
            make(self.db).total()
        self.db.rows[0]["estimated_cost"] = -3
        with self.assertRaises(ledger.LedgerUnavailable):
            make(self.db).total()

    def test_the_pipeline_checks_the_ledger_before_taking_a_credit(self):
        self.db.read_error = ConnectionError("db down")
        credits = []
        ports = pipeline.Ports(image_provider=sample.PlaceholderImageProvider(), voice_provider=None, reserve_credit=lambda: credits.append(1) or True,
                               env={"STORY_IMAGE_USD_EACH": "0.08", "ELEVENLABS_USD_PER_1K_CHARS": "0.18", "SCRIPT_PRICE_IN_PER_M": "1", "SCRIPT_PRICE_OUT_PER_M": "4",
                                    "STORY_PLAN_TOKENS_IN": "4000", "STORY_PLAN_TOKENS_OUT": "3500", "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0.01"},
                               ledger=make(self.db, 2.0))
        with self.assertRaisesRegex(pipeline.PipelineError, "ledger"):
            pipeline.run({"content_format": "story_visual", "story_plan": plan()}, ports, self.tmp / "w", tenant_id="t1")
        self.assertEqual(credits, [])


class TestConcurrentWorkers(Tmp):
    def test_two_workers_that_read_the_same_total_cannot_both_pass(self):
        led_a, led_b = make(self.db, 0.10), make(self.db, 0.10)
        led_a.reserve("image:s1", 0.05)  # total 0.05

        def slip_in(db):  # between B's read (0.05) and B's insert, another worker appends the next row
            db.rows.append({"content_item_id": ITEM, "kind": "image", "input_hash": ledger.LEDGER_PREFIX + "000002", "estimated_cost": 0.05,
                            "storage_path": "", "provider": "ledger:reserved:other"})
        self.db.before_insert = slip_in
        with self.assertRaises(cost.BudgetExceeded) as raised:
            led_b.reserve("image:s2", 0.05)  # B retries after the unique violation, re-reads 0.10 and refuses ON THE CEILING (not on a busy ledger)
        self.assertNotIsInstance(raised.exception, ledger.LedgerUnavailable)
        self.assertIn("episode ceiling", str(raised.exception))
        self.assertEqual(make(self.db, 0.10).total(), 0.10)

    def test_many_workers_racing_never_exceed_the_ceiling(self):
        results, barrier = [], threading.Barrier(12)

        def worker(n):
            led = make(self.db, 1.00)  # each worker has its own ledger object, like separate runners
            barrier.wait()
            try:
                led.reserve(f"image:w{n}", 0.25)
                results.append("ok")
            except cost.BudgetExceeded:
                results.append("refused")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count("ok"), 4)  # exactly cap / amount
        self.assertEqual(make(self.db, 1.00).total(), 1.00)
        sequence = sorted(r["input_hash"] for r in self.db.rows)
        self.assertEqual(len(sequence), len(set(sequence)))  # one row per sequence number

    def test_the_ledger_of_one_episode_never_counts_another(self):
        other = "99999999-2222-4333-8444-555555555555"
        make(self.db, 0.10, other).reserve("image:s1", 0.10)
        make(self.db, 0.10).reserve("image:s1", 0.10)  # the first episode is untouched
        self.assertEqual((make(self.db, 0.10).total(), make(self.db, 0.10, other).total()), (0.10, 0.10))


if __name__ == "__main__":
    unittest.main()
