import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import repo


class TestGenerationCreditReservation(unittest.TestCase):
    def _client_returning(self, value):
        response = Mock(data=value)
        rpc_call = Mock()
        rpc_call.execute.return_value = response
        client = Mock()
        client.rpc.return_value = rpc_call
        return client

    def test_reservation_returns_database_decision(self):
        client = self._client_returning(True)

        self.assertTrue(repo.reserve_generation_credit(client, "item-1"))
        client.rpc.assert_called_once_with(
            "reserve_generation_credit", {"p_content_item_id": "item-1"}
        )

    def test_reservation_rejects_exhausted_balance(self):
        client = self._client_returning(False)

        self.assertFalse(repo.reserve_generation_credit(client, "item-1"))

    def test_refund_returns_whether_reservation_was_active(self):
        client = self._client_returning(True)

        self.assertTrue(repo.refund_generation_credit(client, "item-1"))
        client.rpc.assert_called_once_with(
            "refund_generation_credit", {"p_content_item_id": "item-1"}
        )


if __name__ == "__main__":
    unittest.main()
