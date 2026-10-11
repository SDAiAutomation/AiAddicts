import unittest
from unittest.mock import Mock
from engine.creative_quality_writer import store_report

class WriterTests(unittest.TestCase):
    def setUp(self):
        self.report = {"schema_version":"creative_quality:v1","stage":"script",
                       "decision":"pass","issues":[],"enforcement_enabled":False,
                       "automatic_edits_applied":False}

    def test_rpc_receives_version(self):
        client = Mock()
        client.rpc.return_value.execute.return_value.data = True
        self.assertTrue(store_report(client, "content-id", self.report, script_version=4))
        args = client.rpc.call_args.args
        self.assertEqual(args[0], "store_creative_quality_report")
        self.assertEqual(args[1]["p_report"]["script_version"], 4)

    def test_stale_returns_false(self):
        client = Mock()
        client.rpc.return_value.execute.return_value.data = False
        self.assertFalse(store_report(client, "content-id", self.report, script_version=4))

    def test_unexpected_response_fails_closed(self):
        client = Mock()
        client.rpc.return_value.execute.return_value.data = None
        with self.assertRaises(RuntimeError):
            store_report(client, "content-id", self.report, script_version=4)

if __name__ == "__main__":
    unittest.main()
