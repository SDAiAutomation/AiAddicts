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


if __name__ == "__main__":
    unittest.main()
