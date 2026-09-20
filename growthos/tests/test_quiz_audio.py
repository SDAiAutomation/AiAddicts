import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import video


class TestQuizAudio(unittest.TestCase):
    def test_countdown_places_ticks_after_narration(self):
        source = Path(tempfile.mkdtemp()) / "voice.mp3"
        source.write_bytes(b"audio")
        output = source.with_name("mixed.mp3")
        with patch("engine.video._run") as run:
            video.add_countdown_sfx(str(source), 2.5, 3, str(output), "automatic", "arcade")
        command = run.call_args.args[0]
        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("adelay=2500|2500", graph)
        self.assertIn("adelay=4500|4500", graph)
        self.assertIn("frequency=1220", " ".join(command))

    def test_disabled_effects_use_plain_padding(self):
        with patch("engine.video.pad_audio", return_value="out.mp3") as pad:
            result = video.add_countdown_sfx("voice.mp3", 2, 4, "out.mp3", "off")
        self.assertEqual(result, "out.mp3")
        pad.assert_called_once_with("voice.mp3", 4, "out.mp3")


if __name__ == "__main__":
    unittest.main()
