"""Offline end-to-end test using a real generated WAV and the existing FFmpeg duration probe."""
import json
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from growthos.engine.story_intelligence.audio_adapter import prepare_aligned_storyboard


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for real decoded audio probing")
class RealAudioIntegrationTests(unittest.TestCase):
    def test_two_real_wav_files_are_measured_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for sid, seconds in (("shot_01", 1), ("shot_02", 2)):
                filename = Path(directory) / (sid + ".wav")
                with wave.open(str(filename), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(struct.pack("<h", 0) * 8000 * seconds)
                paths[sid] = str(filename)
            story = {
                "target_duration_s": 5,
                "characters": [{"id": "neo"}, {"id": "orion"}],
                "shots": [
                    {"id": "shot_01", "speaker_id": "neo", "dialogue": "Bonjour", "duration_s": 2},
                    {"id": "shot_02", "speaker_id": "orion", "dialogue": "Bonjour", "duration_s": 3},
                ],
            }
            aligned, report = prepare_aligned_storyboard(story, paths)
            self.assertTrue(report["ready_for_render"])
            self.assertAlmostEqual(aligned["shots"][0]["measured_audio_duration_s"], 1, delta=0.02)
            self.assertAlmostEqual(aligned["shots"][1]["measured_audio_duration_s"], 2, delta=0.02)
            self.assertEqual(report["audio_durations_source"], "local_audio_files_probed")


if __name__ == "__main__":
    unittest.main()
