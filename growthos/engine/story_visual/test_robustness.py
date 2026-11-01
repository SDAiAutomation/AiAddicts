"""Operational robustness of the illustrated-story engine, offline and deterministic (stub providers, in-memory remote store, fake DB client):
A. fail fast: no later scene is paid for after a scene fails;  B. resume without paying twice: a fresh ephemeral runner restores the
already generated images and voices from the shared asset cache;  C. the quota is read from shared state and fails closed."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from growthos.engine.story_visual import cache, cost, orchestrator, quota, sample, voice

VOICE = "VoiceId12345"
UNIT = 0.05


def plan():
    p = sample.moral_plan()
    p["voice_id"] = VOICE
    return p


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def images(self, provider, work, disk_cache=None, tracker=None):
        return orchestrator.generate_scene_images(plan(), tenant_id="t1", work_dir=work, provider=provider,
                                                  tracker=tracker or cost.BudgetTracker(cost.Budget()), expected_unit_usd=UNIT, disk_cache=disk_cache)


class FailAt:
    """Image provider that fails on its n-th call (1-based) and works otherwise; counts calls."""

    def __init__(self, n):
        self.inner, self.n, self.calls = sample.PlaceholderImageProvider(), n, 0

    def __call__(self, prompt, out_path, **kw):
        self.calls += 1
        if self.calls == self.n:
            return orchestrator.ImageResult(None, 0.0, None, "provider_error")
        return self.inner(prompt, out_path, **kw)


class TestFailFast(Tmp):
    def test_no_later_image_is_paid_after_a_failure_and_the_retry_resumes_at_the_failed_scene(self):
        provider = FailAt(3)
        manifest = self.images(provider, self.tmp / "w")
        self.assertEqual(provider.calls, 3)  # s1, s2 ok, s3 fails: s4..s8 are never requested
        self.assertEqual({k: v["status"] for k, v in manifest.items()}, {"s1": "done", "s2": "done", "s3": "failed"})
        again = FailAt(0)  # never fails
        manifest = self.images(again, self.tmp / "w")
        self.assertEqual(again.calls, 6)  # s1, s2 are idempotent; s3..s8 are generated now
        self.assertTrue(all(m["status"] == "done" for m in manifest.values()) and len(manifest) == 8)

    def test_no_later_voice_is_paid_after_a_failure(self):
        class Flaky(voice.SimulatedVoiceProvider):
            def __call__(self, text, voice_id, out_path):
                if len(self.calls) == 1:  # the second call fails
                    self.calls.append(text)
                    return voice.VoiceResult(None, None, None, "voice_error: simulated")
                return super().__call__(text, voice_id, out_path)
        provider = Flaky("en")
        manifest = voice.synthesize_story(plan(), tenant_id="t1", work_dir=self.tmp / "w", provider=provider,
                                          tracker=cost.BudgetTracker(cost.Budget()), voice_id=None, rate_per_1k=0.18, disk_cache=None)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual({k: v["status"] for k, v in manifest.items()}, {"s1": "done", "s2": "failed"})


class FakeRemote:
    """In-memory stand-in for `asset_store` (the shared bucket): survives the loss of the local runner disk."""

    def __init__(self):
        self.files: dict[tuple[str, str], bytes] = {}

    def restore(self, kind, key, dest):
        data = self.files.get((kind, key))
        if data is None:
            return False
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return True

    def save(self, kind, key, src, estimated_cost=None, provider=None):
        self.files[(kind, key)] = Path(src).read_bytes()
        return True


class TestResumeWithoutPayingTwice(Tmp):
    def patched(self, remote):
        return patch.multiple("growthos.engine.asset_store", restore_asset=remote.restore, save_asset=remote.save)

    def test_a_fresh_runner_restores_paid_images_instead_of_regenerating_them(self):
        remote = FakeRemote()
        with self.patched(remote):
            first = sample.PlaceholderImageProvider()
            self.images(first, self.tmp / "run1", cache.PersistentCache(self.tmp / "run1-cache", "t1"))
            self.assertEqual(len(first.calls), 8)
            # the runner is ephemeral: new work dir AND new local cache, only the remote store survives
            second, tracker = sample.PlaceholderImageProvider(), cost.BudgetTracker(cost.Budget())
            manifest = self.images(second, self.tmp / "run2", cache.PersistentCache(self.tmp / "run2-cache", "t1"), tracker)
        self.assertEqual(second.calls, [])
        self.assertTrue(all(m["cache_hit"] and m["cost_kind"] == cost.CACHED for m in manifest.values()))
        self.assertEqual(tracker.total, 0.0)

    def test_a_corrupted_remote_image_is_rejected_and_regenerated(self):
        remote = FakeRemote()
        with self.patched(remote):
            self.images(sample.PlaceholderImageProvider(), self.tmp / "run1", cache.PersistentCache(self.tmp / "c1", "t1"))
            for key in list(remote.files):
                remote.files[key] = b"not an image"
            second = sample.PlaceholderImageProvider()
            manifest = self.images(second, self.tmp / "run2", cache.PersistentCache(self.tmp / "c2", "t1"))
        self.assertEqual(len(second.calls), 8)  # never trust a restored file blindly
        self.assertTrue(all(m["status"] == "done" and not m["cache_hit"] for m in manifest.values()))

    def test_without_the_shared_cache_it_behaves_like_the_disk_cache(self):
        first, second = sample.PlaceholderImageProvider(), sample.PlaceholderImageProvider()
        self.images(first, self.tmp / "run1", cache.PersistentCache(self.tmp / "c1", "t1"))
        self.images(second, self.tmp / "run2", cache.PersistentCache(self.tmp / "c2", "t1"))  # asset_store is not configured: nothing shared
        self.assertEqual((len(first.calls), len(second.calls)), (8, 8))

    def test_a_fresh_runner_restores_paid_voices_with_their_word_timings(self):
        remote = FakeRemote()
        def synth(work, cache_dir, provider):
            return voice.synthesize_story(plan(), tenant_id="t1", work_dir=work, provider=provider, tracker=cost.BudgetTracker(cost.Budget()),
                                          voice_id=None, rate_per_1k=0.18, disk_cache=cache.PersistentCache(cache_dir, "t1", ".mp3"))
        with self.patched(remote):
            first = voice.SimulatedVoiceProvider("en")
            synth(self.tmp / "v1", self.tmp / "vc1", first)
            second = voice.SimulatedVoiceProvider("en")
            manifest = synth(self.tmp / "v2", self.tmp / "vc2", second)
        self.assertEqual((len(first.calls), len(second.calls)), (8, 0))
        self.assertTrue(all(m["cache_hit"] and m["words"] for m in manifest.values()))
        self.assertTrue({"voice", "voice_words"} <= {kind for kind, _ in remote.files})


class FakeClient:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.filters = rows or [], error, []

    def table(self, name):
        self.filters.append(("table", name))
        return self

    def select(self, *a):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def gte(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        if self.error:
            raise self.error
        return type("R", (), {"data": self.rows})()


class TestSharedQuota(unittest.TestCase):
    NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def make(self, rows=None, error=None, limit=2, item="cur", org="org1"):
        client = FakeClient(rows, error)
        return quota.SharedQuota(client, org, item, limit, now=lambda: self.NOW), client

    def test_counts_other_stories_of_the_organisation_in_the_window(self):
        q, client = self.make([{"content_item_id": "a"}, {"content_item_id": "b"}], limit=3)
        self.assertTrue(q.consume())
        self.assertIn(("organization_id", "org1"), client.filters)
        self.assertIn(("props->>renderer", "story_visual"), client.filters)
        self.assertIn(("created_at", (self.NOW - timedelta(days=1)).isoformat()), client.filters)

    def test_refuses_at_the_limit_and_counts_a_resumed_story_once(self):
        self.assertFalse(self.make([{"content_item_id": "a"}, {"content_item_id": "b"}], limit=2)[0].consume())
        self.assertTrue(self.make([{"content_item_id": "a"}, {"content_item_id": "a"}, {"content_item_id": "a"}], limit=2)[0].consume())
        self.assertTrue(self.make([{"content_item_id": "cur"}], limit=1)[0].consume())  # the current story never counts against itself

    def test_fails_closed(self):
        self.assertFalse(self.make(error=RuntimeError("db down"))[0].consume())
        self.assertFalse(self.make(limit=0)[0].consume())
        self.assertFalse(self.make(org="")[0].consume())

    def test_state_is_read_each_time_not_kept_in_memory(self):
        q, client = self.make([], limit=1)
        self.assertTrue(q.consume())
        client.rows = [{"content_item_id": "other"}]  # another worker started a story meanwhile
        self.assertFalse(q.consume())


if __name__ == "__main__":
    unittest.main()
