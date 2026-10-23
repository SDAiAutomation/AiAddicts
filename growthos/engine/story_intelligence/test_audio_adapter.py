"""Tests avoid paid APIs, real voice synthesis and external network."""
import tempfile
import unittest
from pathlib import Path
from growthos.engine.story_intelligence.audio_adapter import measure_audio_files, prepare_aligned_storyboard


class AudioAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audio = Path(self.temp.name) / "sample.mp3"
        self.audio.write_bytes(b"fake audio for injected probe only")

    def test_probe_injection(self):
        self.assertEqual(measure_audio_files({"s1": str(self.audio)}, duration_probe=lambda _: 2.5), {"s1": 2.5})

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            measure_audio_files({"s1": str(self.audio) + ".missing"}, duration_probe=lambda _: 2.5)

    def test_invalid_probe_result(self):
        with self.assertRaises(ValueError):
            measure_audio_files({"s1": str(self.audio)}, duration_probe=lambda _: float("nan"))

    def test_alignment_with_probe(self):
        story = {"target_duration_s": 5, "characters": [{"id": "neo"}], "shots": [{"id": "s1", "speaker_id": "neo", "dialogue": "Non.", "duration_s": 5}]}
        aligned, report = prepare_aligned_storyboard(story, {"s1": str(self.audio)}, duration_probe=lambda _: 4.0)
        self.assertTrue(report["fits_target"])
        self.assertEqual(report["audio_durations_source"], "local_audio_files_probed")
        self.assertEqual(aligned["shots"][0]["duration_s"], 5)

    def test_overrun_not_ready(self):
        story = {"target_duration_s": 5, "characters": [{"id": "neo"}], "shots": [{"id": "s1", "speaker_id": "neo", "dialogue": "Non.", "duration_s": 5}]}
        _, report = prepare_aligned_storyboard(story, {"s1": str(self.audio)}, duration_probe=lambda _: 6.0)
        self.assertFalse(report["ready_for_render"])


if __name__ == "__main__":
    unittest.main()
