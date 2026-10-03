import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import events


class TestEvents(unittest.TestCase):
    def test_record_inserts_event_with_non_null_props_only(self):
        client = MagicMock()
        events.record(client, "generation_completed", "item", "org", cost_usd=0.34, version=None, status="video")
        row = client.table.return_value.insert.call_args[0][0]
        self.assertEqual(row["event"], "generation_completed")
        self.assertEqual(row["organization_id"], "org")
        self.assertEqual(row["props"], {"cost_usd": 0.34, "status": "video"})

    def test_record_without_organization_does_nothing(self):
        client = MagicMock()
        events.record(client, "generation_started", "item", None)
        client.table.assert_not_called()

    def test_record_never_raises(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = RuntimeError("db down")
        events.record(client, "generation_failed", "item", "org", error="x")

    def test_organization_lookup_never_raises(self):
        client = MagicMock()
        client.table.side_effect = RuntimeError("db down")
        self.assertIsNone(events.organization_id_of(client, "item"))

    def test_organization_lookup_reads_nested_account(self):
        client = MagicMock()
        chain = client.table.return_value.select.return_value.eq.return_value.single.return_value
        chain.execute.return_value.data = {"accounts": {"organization_id": "org-1"}}
        self.assertEqual(events.organization_id_of(client, "item"), "org-1")


if __name__ == "__main__":
    unittest.main()
