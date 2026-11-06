"""Post-render checks must measure both streams, not only the container."""
import unittest

from growthos.engine.story_visual.pipeline import quality_issues


def info(audio_start="0", audio_duration="60"):
    return {"duration": 60, "video": {"width": 1080, "height": 1920,
            "codec_name": "h264", "pix_fmt": "yuv420p", "start_time": "0", "duration": "60"},
            "audio": {"codec_name": "aac", "start_time": audio_start, "duration": audio_duration}}


class TestStreamSync(unittest.TestCase):
    def test_streams_in_sync(self):
        self.assertEqual(quality_issues(info(audio_duration="59.9"), {"total_s": 60}), [])

    def test_stream_drift_and_missing_timing_require_review(self):
        self.assertTrue(any("timing differs" in x for x in quality_issues(info(audio_duration="59.8"), {"total_s": 60})))
        self.assertTrue(any("timing differs" in x for x in quality_issues(info(audio_start="0.2", audio_duration="59.8"), {"total_s": 60})))
        self.assertTrue(any("unavailable" in x for x in quality_issues(info(audio_duration="nan"), {"total_s": 60})))


if __name__ == "__main__":
    unittest.main()
