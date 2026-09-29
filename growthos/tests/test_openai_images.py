import unittest
from unittest.mock import Mock, patch

from engine import openai_images


class TestImageRateLimit(unittest.TestCase):
    def test_request_starts_are_spaced(self):
        clock = [100.0]

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(openai_images.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(openai_images.time, "sleep", side_effect=sleep):
            openai_images._next_request_at = 0.0
            openai_images._wait_for_image_slot()
            self.assertEqual(clock[0], 100.0)
            openai_images._wait_for_image_slot()
            self.assertEqual(clock[0], 113.0)
        openai_images._next_request_at = 0.0

    def test_429_respects_provider_delay_before_retry(self):
        limited = Mock(status_code=429, text="Please try again in 12s.", headers={})
        success = Mock(status_code=200, text="", headers={})
        with patch.object(openai_images, "_wait_for_image_slot") as wait, \
             patch.object(openai_images, "_defer_image_requests") as defer, \
             patch.object(openai_images.time, "sleep") as sleep, \
             patch.object(openai_images.requests, "post", side_effect=[limited, success]) as post:
            result = openai_images._post_with_retry("https://example.test", {}, 90)
        self.assertIs(result, success)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(wait.call_count, 2)
        defer.assert_called_once_with(12.0)
        sleep.assert_not_called()

    def test_retry_after_header_takes_priority(self):
        response = Mock(headers={"Retry-After": "25"}, text="Please try again in 12s.")
        self.assertEqual(openai_images._rate_limit_delay(response), 25.0)


class TestUsageExtraction(unittest.TestCase):
    def test_usage_is_normalised_and_popped_once(self):
        import base64, tempfile, os
        body = {
            "data": [{"b64_json": base64.b64encode(b"x").decode()}],
            "usage": {
                "input_tokens": 300,
                "input_tokens_details": {"text_tokens": 100, "image_tokens": 200},
                "output_tokens": 4000,
            },
        }
        resp = Mock()
        resp.json.return_value = body
        with tempfile.TemporaryDirectory() as tmp:
            openai_images._decode_and_write(resp, os.path.join(tmp, "a.jpg"))
        self.assertEqual(
            openai_images.pop_last_usage(), {"input_text": 100, "input_image": 200, "output": 4000}
        )
        self.assertIsNone(openai_images.pop_last_usage())

    def test_missing_usage_is_none(self):
        self.assertIsNone(openai_images._extract_usage({"data": []}))


class TestErrorTracking(unittest.TestCase):
    """Phase 2.6 (benchmark fix) : `pop_last_error` doit exposer la même
    catégorie que `_classify_error` aurait loguée, pour que `visuals.py`
    puisse journaliser POURQUOI une scène a basculé en repli — voir
    `visuals._build_fallback_events`. Même contrat "pop-once" que
    `pop_last_usage`."""

    def test_content_policy_rejection_is_recorded_and_popped_once(self):
        # Texte calqué sur le rejet réel observé pendant le benchmark visuel
        # (voir engine/openai_images._classify_error : détecté via "safety").
        rejection = Mock(
            status_code=400,
            text='{"error": {"message": "Your request was rejected by the safety system.", "code": "moderation_block"}}',
            headers={},
        )
        with patch.dict(openai_images.os.environ, {"OPENAI_API_KEY": "test-key"}), \
             patch.object(openai_images, "_wait_for_image_slot"), \
             patch.object(openai_images.requests, "post", return_value=rejection):
            path = openai_images.generate_image("un prompt", "/tmp/out.jpg", "9:16")
        self.assertIsNone(path)
        self.assertEqual(openai_images.pop_last_error(), "content_policy")
        self.assertIsNone(openai_images.pop_last_error())  # popped once, like pop_last_usage

    def test_network_failure_is_recorded_as_unknown(self):
        with patch.dict(openai_images.os.environ, {"OPENAI_API_KEY": "test-key"}), \
             patch.object(openai_images, "_wait_for_image_slot"), \
             patch.object(openai_images.requests, "post", side_effect=ValueError("boom")):
            path = openai_images.generate_image("un prompt", "/tmp/out.jpg", "9:16")
        self.assertIsNone(path)
        self.assertEqual(openai_images.pop_last_error(), "unknown")

    def test_success_does_not_leave_a_stale_error(self):
        import base64
        success = Mock(status_code=200, text="", headers={})
        success.json.return_value = {"data": [{"b64_json": base64.b64encode(b"x").decode()}]}
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(openai_images.os.environ, {"OPENAI_API_KEY": "test-key"}), \
                 patch.object(openai_images, "_wait_for_image_slot"), \
                 patch.object(openai_images.requests, "post", return_value=success):
                path = openai_images.generate_image("un prompt", os.path.join(tmp, "a.jpg"), "9:16")
        self.assertIsNotNone(path)
        self.assertIsNone(openai_images.pop_last_error())


if __name__ == "__main__":
    unittest.main()
