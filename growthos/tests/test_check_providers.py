import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import check_providers


def _response(status, body=None):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.json.return_value = body or {}
    return resp


class TestOpenAICheck(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"OPENAI_API_KEY": "k", "HEALTH_OPENAI_MODEL": "m"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _run(self, resp):
        with patch.object(check_providers.requests, "post", return_value=resp):
            return check_providers.check_openai()

    def test_ok(self):
        self.assertEqual(self._run(_response(200)), ([], []))

    def test_exhausted_credit_is_a_problem(self):
        problems, _ = self._run(_response(429, {"error": {"code": "credit_balance_exhausted"}}))
        self.assertEqual([key for key, _ in problems], ["openai:credit"])

    def test_insufficient_quota_is_a_problem(self):
        problems, _ = self._run(_response(429, {"error": {"code": "insufficient_quota"}}))
        self.assertEqual([key for key, _ in problems], ["openai:credit"])

    def test_rate_limit_is_only_a_note(self):
        problems, notes = self._run(_response(429, {"error": {"code": "rate_limit_exceeded"}}))
        self.assertEqual(problems, [])
        self.assertTrue(notes)

    def test_bad_key_is_a_problem(self):
        problems, _ = self._run(_response(401))
        self.assertEqual([key for key, _ in problems], ["openai:auth"])

    def test_model_not_configured_is_a_note(self):
        os.environ.pop("HEALTH_OPENAI_MODEL")
        problems, notes = check_providers.check_openai()
        self.assertEqual(problems, [])
        self.assertTrue(notes)


class TestElevenLabsCheck(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {"ELEVENLABS_API_KEY": "k"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_low_remaining_characters_is_a_problem(self):
        sub = {"character_limit": 100_000, "character_count": 95_000, "status": "active"}
        with patch.object(check_providers.requests, "get", return_value=_response(200, sub)):
            problems, _ = check_providers.check_elevenlabs()
        self.assertEqual([key for key, _ in problems], ["elevenlabs:credit"])

    def test_enough_characters(self):
        sub = {"character_limit": 100_000, "character_count": 10_000, "status": "active"}
        with patch.object(check_providers.requests, "get", return_value=_response(200, sub)):
            problems, notes = check_providers.check_elevenlabs()
        self.assertEqual(problems, [])
        self.assertIn("90,000", notes[0])

    def test_restricted_key_without_subscription_scope_is_a_note(self):
        with patch.object(check_providers.requests, "get", side_effect=[_response(401), _response(200)]):
            problems, notes = check_providers.check_elevenlabs()
        self.assertEqual(problems, [])
        self.assertTrue(notes)

    def test_rejected_key_is_a_problem(self):
        with patch.object(check_providers.requests, "get", side_effect=[_response(401), _response(401)]):
            problems, _ = check_providers.check_elevenlabs()
        self.assertEqual([key for key, _ in problems], ["elevenlabs:auth"])


class TestReport(unittest.TestCase):
    def test_report_lists_problems_and_notes(self):
        report = check_providers.build_report(
            [("openai:credit", "OpenAI : crédit épuisé")], ["note"], datetime(2026, 9, 25, tzinfo=timezone.utc),
        )
        self.assertIn("- OpenAI : crédit épuisé", report)
        self.assertIn("- note", report)

    def test_report_without_problem(self):
        report = check_providers.build_report([], [], datetime(2026, 9, 25, tzinfo=timezone.utc))
        self.assertIn("Aucun problème.", report)


if __name__ == "__main__":
    unittest.main()
