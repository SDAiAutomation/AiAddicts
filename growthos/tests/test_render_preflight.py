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
                       return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")):
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
                       return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")):
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

    def _inspect_with_av_log(self, log, returncode=0):
        payload = {"format": {"duration": "30"}, "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}]}
        probe = SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        av = SimpleNamespace(returncode=returncode, stdout="", stderr=log)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "clip.mp4"
            file.write_bytes(b"mock")
            with patch("engine.render_preflight.subprocess.run", side_effect=[probe, av]):
                return inspect_video(str(file))

    def test_clean_av_log_passes(self):
        report = self._inspect_with_av_log("[Parsed_volumedetect_1] mean_volume: -22.4 dB\n")
        self.assertEqual(report["decision"], "pass")

    def test_long_silence_and_freeze_are_review_not_block(self):
        report = self._inspect_with_av_log(
            "[silencedetect] silence_duration: 3.2\n"
            "[freezedetect] lavfi.freezedetect.freeze_duration: 5.0\n"
            "mean_volume: -20.0 dB\n")
        self.assertEqual(report["decision"], "review")
        self.assertEqual({i["code"] for i in report["issues"]}, {"long_silence", "frozen_video"})
        self.assertTrue(all(i["severity"] == "warning" for i in report["issues"]))

    def test_freeze_running_to_the_end_is_detected(self):
        # ffmpeg prints freeze_start but no freeze_duration when the freeze lasts until EOF (30 s clip).
        report = self._inspect_with_av_log("lavfi.freezedetect.freeze_start: 20\nmean_volume: -20.0 dB\n")
        self.assertEqual([i["code"] for i in report["issues"]], ["frozen_video"])

    def test_quiet_audio_flagged(self):
        report = self._inspect_with_av_log("mean_volume: -45.0 dB\n")
        self.assertEqual([i["code"] for i in report["issues"]], ["audio_too_quiet"])

    def test_av_failure_is_info_and_does_not_force_review(self):
        report = self._inspect_with_av_log("boom", returncode=1)
        self.assertEqual(report["issues"][0]["code"], "av_check_unavailable")
        self.assertEqual(report["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
