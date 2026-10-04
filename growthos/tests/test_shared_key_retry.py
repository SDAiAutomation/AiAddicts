import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import retry, tts, visuals


def _response(status, text="", retry_after=None, content=b""):
    resp = Mock(status_code=status, text=text, content=content)
    resp.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return resp


class TestRetryDelay(unittest.TestCase):
    def test_provider_delay_wins_and_is_capped(self):
        self.assertEqual(retry.retry_delay(1, _response(429, retry_after="7")), 7.0)
        self.assertEqual(retry.retry_delay(1, _response(429, retry_after="999")), retry.RETRY_AFTER_CAP_SECONDS)
        self.assertEqual(retry.retry_delay(1, _response(429, retry_after="999"), cap=10.0), 10.0)

    def test_backoff_grows_stays_bounded_and_has_jitter(self):
        self.assertTrue(2.0 <= retry.retry_delay(1) <= 3.0)
        self.assertTrue(retry.retry_delay(10) <= 17.0)

    def test_unusable_header_falls_back_to_backoff(self):
        self.assertTrue(retry.retry_delay(1, _response(429, retry_after="demain")) >= 2.0)
        self.assertTrue(retry.retry_delay(1, object()) >= 2.0)


class TestElevenLabsRetry(unittest.TestCase):
    def _synthesize(self, responses):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(tts.requests, "post", side_effect=responses) as post, \
                patch.object(tts.time, "sleep") as sleep:
            try:
                result = tts.synthesize("Bonjour", "voice", str(Path(tmp) / "a.mp3"), api_key="k")
            except RuntimeError as exc:
                result = exc
        return result, post, sleep

    def test_a_429_from_another_organisation_is_waited_out(self):
        result, post, sleep = self._synthesize([_response(429, "busy", retry_after="2"), _response(200, content=b"mp3")])
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(2.0)
        self.assertTrue(str(result).endswith("a.mp3"))

    def test_persistent_429_fails_loudly_with_an_explicit_reason(self):
        result, post, _ = self._synthesize([_response(429, "busy")] * 5)
        self.assertEqual(post.call_count, 5)
        self.assertIsInstance(result, RuntimeError)
        self.assertIn("5 tentatives", str(result))
        self.assertIn("limite de débit ElevenLabs", str(result))

    def test_other_4xx_fails_fast(self):
        result, post, sleep = self._synthesize([_response(401, "bad key")])
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("HTTP 401", str(result))


class TestPexelsRetry(unittest.TestCase):
    def test_429_is_retried_then_succeeds(self):
        ok = _response(200)
        ok.json.return_value = {"photos": [{"src": {"large": "https://img/x.jpg"}}]}
        ok.raise_for_status.return_value = None
        with patch.object(visuals.requests, "get", side_effect=[_response(429, retry_after="1"), ok]) as get, \
                patch.object(visuals.time, "sleep") as sleep:
            self.assertEqual(visuals.search_image_url("chat", "key"), "https://img/x.jpg")
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_persistent_429_returns_none_and_says_why(self):
        bad = _response(429)
        bad.raise_for_status.side_effect = visuals.requests.HTTPError("429")
        with patch.object(visuals.requests, "get", return_value=bad) as get, \
                patch.object(visuals.time, "sleep"), patch("builtins.print") as printed:
            self.assertIsNone(visuals.search_image_url("chat", "key"))
        self.assertEqual(get.call_count, 3)
        self.assertTrue(any("Pexels" in str(call.args[0]) for call in printed.call_args_list))

    def test_client_error_is_not_retried(self):
        bad = _response(401)
        bad.raise_for_status.side_effect = visuals.requests.HTTPError("401")
        with patch.object(visuals.requests, "get", return_value=bad) as get, patch.object(visuals.time, "sleep") as sleep:
            self.assertIsNone(visuals.search_image_url("chat", "key"))
        self.assertEqual(get.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
