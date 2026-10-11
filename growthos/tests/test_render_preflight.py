import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from engine.render_preflight import inspect_video


class RenderPreflightTests(unittest.TestCase):
    def test_missing_file(self):
        report = inspect_video("/path/that/does/not/exist.mp4")
        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["issues"][0]["code"], "render_missing")

    def test_valid_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "clip.mp4"
            file.write_bytes(b"mock")
            payload = {"format": {"duration": "12.5"}, "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920},
                {"codec_type": "audio"}]}
            with patch("engine.render_preflight.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload))):
                report = inspect_video(str(file))
            self.assertEqual(report["decision"], "pass")
            self.assertEqual(report["metadata"]["duration"], 12.5)

    def test_no_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "clip.mp4"
            file.write_bytes(b"mock")
            payload = {"format": {"duration": "10"}, "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920}]}
            with patch("engine.render_preflight.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload))):
                report = inspect_video(str(file))
            self.assertEqual(report["decision"], "block")
            self.assertEqual(report["issues"][0]["code"], "audio_stream_missing")

    def test_ffprobe_missing_is_review(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "clip.mp4"
            file.write_bytes(b"mock")
            with patch("engine.render_preflight.subprocess.run", side_effect=FileNotFoundError()):
                report = inspect_video(str(file))
            self.assertEqual(report["decision"], "review")
            self.assertFalse(report["enforcement_enabled"])


if __name__ == "__main__":
    unittest.main()
