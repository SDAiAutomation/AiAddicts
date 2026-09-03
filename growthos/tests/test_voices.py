import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.voices import load_voice_map, resolve_voice

MAP = {"coach-business": "voice-coach", "default": "voice-default"}


class TestResolveVoice(unittest.TestCase):
    def test_override_wins(self):
        script = {"niche": "coach-business", "voice_id": "voice-script"}
        self.assertEqual(resolve_voice(script, "voice-cli", MAP), "voice-cli")

    def test_script_voice_id_used_without_override(self):
        script = {"niche": "coach-business", "voice_id": "voice-script"}
        self.assertEqual(resolve_voice(script, None, MAP), "voice-script")

    def test_niche_map_used(self):
        script = {"niche": "coach-business"}
        self.assertEqual(resolve_voice(script, None, MAP), "voice-coach")

    def test_default_key_fallback(self):
        script = {"niche": "niche-inconnue"}
        self.assertEqual(resolve_voice(script, None, MAP), "voice-default")

    def test_placeholder_is_not_usable(self):
        script = {"niche": "x", "voice_id": "REMPLACER_PAR_UN_VOICE_ID_ELEVENLABS"}
        self.assertEqual(resolve_voice(script, None, MAP), "voice-default")

    def test_raises_when_nothing_usable(self):
        with self.assertRaises(ValueError):
            resolve_voice({"niche": "x"}, None, {})

    def test_whitespace_is_stripped(self):
        self.assertEqual(resolve_voice({"niche": "x"}, "  abc  ", {}), "abc")


class TestLoadVoiceMap(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(load_voice_map(Path(tempfile.gettempdir()) / "nope-voices.json"), {})

    def test_skips_comment_and_non_string_values(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"_note": "hello", "finance": "vid", "bad": ["x"]}, f)
            path = Path(f.name)
        self.assertEqual(load_voice_map(path), {"finance": "vid"})


if __name__ == "__main__":
    unittest.main()
