import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import queue_needs_animation as q  # noqa: E402

from engine.story_animation import contract  # noqa: E402

ANIMATED = {"content_format": "story", "story": {"version": contract.STORY_VERSION}}


def client_with(rows):
    client = MagicMock()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value
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
        client.table.return_value.select.return_value.eq.assert_called_once_with("status", "queued")

    def _run_main(self, side_effect=None, rows=None):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": out}), patch(
                "engine.db.get_service_client", side_effect=side_effect, return_value=client_with(rows or [])
            ):
                code = q.main()
            return code, Path(out).read_text(encoding="utf-8").strip()

    def test_main_writes_true(self):
        self.assertEqual(self._run_main(rows=[{"id": 1, "script": ANIMATED}]), (0, "has_work=true"))

    def test_main_errors_exit_zero_with_false(self):
        self.assertEqual(self._run_main(side_effect=RuntimeError("db down")), (0, "has_work=false"))


if __name__ == "__main__":
    unittest.main()
