import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import queue_needs_animation as q  # noqa: E402

from engine import repo  # noqa: E402
from engine.story_animation import contract  # noqa: E402

ANIMATED = {"content_format": "story", "story": {"version": contract.STORY_VERSION}}


def client_with(rows):
    client = MagicMock()
    chain = client.table.return_value.select.return_value.in_.return_value.order.return_value.limit.return_value
    chain.execute.return_value.data = rows
    return client


class QueueNeedsAnimationTest(unittest.TestCase):
    def test_true_when_an_animated_story_is_queued(self):
        rows = [{"id": 1, "script": {"visual_style": "explainer"}}, {"id": 2, "script": ANIMATED}]
        self.assertTrue(q.queue_has_animated(client_with(rows)))

    def test_false_for_legacy_or_empty_queue(self):
        legacy = [{"id": 1, "script": {"content_format": "story"}}, {"id": 2, "script": None}]
        self.assertFalse(q.queue_has_animated(client_with(legacy)))
        self.assertFalse(q.queue_has_animated(client_with([])))

    def test_only_queued_status_is_read(self):
        client = client_with([])
        q.queue_has_animated(client)
        client.table.return_value.select.return_value.in_.assert_called_once_with("status", ["queued", "generating"])

    def test_stale_generating_animated_item_counts_but_a_fresh_one_does_not(self):
        now = datetime.now(timezone.utc)
        limit = timedelta(minutes=repo._STALE_GENERATING_MINUTES)
        stale = {"id": 1, "script": ANIMATED, "status": "generating", "updated_at": (now - limit - timedelta(minutes=1)).isoformat()}
        fresh = {"id": 2, "script": ANIMATED, "status": "generating", "updated_at": (now - limit + timedelta(minutes=1)).isoformat()}
        legacy_stale = {"id": 3, "script": {"content_format": "story"}, "status": "generating", "updated_at": "2000-01-01T00:00:00Z"}
        self.assertTrue(q.queue_has_animated(client_with([stale])))
        self.assertFalse(q.queue_has_animated(client_with([fresh, legacy_stale])))

    def _run_main(self, config_error=None, query_error=None, rows=None):
        client = client_with(rows or [])
        if query_error:
            client.table.side_effect = query_error
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": out}), patch(
                "engine.db.get_service_client", side_effect=config_error, return_value=client
            ):
                code = q.main()
            return code, Path(out).read_text(encoding="utf-8").strip()

    def test_main_writes_true(self):
        self.assertEqual(self._run_main(rows=[{"id": 1, "script": ANIMATED, "status": "queued"}]), (0, "has_work=true"))

    def test_configuration_error_fails_the_job_red(self):
        self.assertEqual(self._run_main(config_error=RuntimeError("SUPABASE_URL manquant")), (1, "has_work=false"))

    def test_transient_query_error_is_non_blocking_with_a_warning(self):
        with patch("sys.stderr") as err:
            result = self._run_main(query_error=RuntimeError("timeout"))
        self.assertEqual(result, (0, "has_work=false"))
        self.assertIn("::warning::", "".join(c.args[0] for c in err.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
