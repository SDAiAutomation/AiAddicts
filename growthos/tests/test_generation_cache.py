import unittest
from unittest.mock import patch

from engine import generation_cache


SCRIPT = {
    "title": "Test", "niche": "business", "account": "compte",
    "blocks": [{"role": "hook", "text": "Une erreur coûteuse"}],
}


class TestGenerationFingerprint(unittest.TestCase):
    @patch("engine.generation_cache._code_digest", return_value="code-v1")
    def test_same_inputs_have_same_fingerprint(self, _digest):
        self.assertEqual(
            generation_cache.fingerprint(SCRIPT, "voice-a"),
            generation_cache.fingerprint(SCRIPT, "voice-a"),
        )

    @patch("engine.generation_cache._code_digest", return_value="code-v1")
    def test_script_or_voice_change_invalidates_cache(self, _digest):
        original = generation_cache.fingerprint(SCRIPT, "voice-a")
        changed = {**SCRIPT, "blocks": [{"role": "hook", "text": "Un autre hook"}]}
        self.assertNotEqual(original, generation_cache.fingerprint(changed, "voice-a"))
        self.assertNotEqual(original, generation_cache.fingerprint(SCRIPT, "voice-b"))

    def test_code_change_invalidates_cache(self):
        with patch("engine.generation_cache._code_digest", return_value="code-v1"):
            first = generation_cache.fingerprint(SCRIPT, "voice-a")
        with patch("engine.generation_cache._code_digest", return_value="code-v2"):
            second = generation_cache.fingerprint(SCRIPT, "voice-a")
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
