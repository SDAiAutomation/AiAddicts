"""Offline tests: never invoke ElevenLabs."""
import json
import tempfile
import unittest
from pathlib import Path
from growthos.engine.story_intelligence.voice_pilot import run


class VoicePilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.story = Path(self.temp.name) / "story.json"
        self.story.write_text(json.dumps({
            "target_duration_s": 5,
            "characters": [{"id": "neo"}],
            "shots": [{"id": "s1", "speaker_id": "neo", "dialogue": "Bonjour", "duration_s": 5}]
        }), encoding="utf-8")

    def test_preview_never_generates_audio(self):
        output = Path(self.temp.name) / "output"
        result = run(str(self.story), str(output), {}, generate=False)
        self.assertEqual(result["paid_requests"], 0)
        self.assertFalse(output.exists())

    def test_missing_voice_id_fails_before_api(self):
        with self.assertRaises(ValueError):
            run(str(self.story), str(Path(self.temp.name) / "output"), {}, generate=True)

    def test_missing_key_fails_before_api(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"ELEVENLABS_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                run(str(self.story), str(Path(self.temp.name) / "output"), {"neo": "test_voice"}, generate=True)

    def test_invalid_story_fails_before_api(self):
        self.story.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            run(str(self.story), str(Path(self.temp.name) / "output"), {}, generate=False)


if __name__ == "__main__":
    unittest.main()
