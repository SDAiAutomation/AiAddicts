"""Smoke tests for the isolated renderer. Requires Pillow and ffmpeg."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from growthos.engine.story_animation_spike.render_demo import DEMO, draw_frame, render_demo


class RenderDemoTests(unittest.TestCase):
    def test_frame_dimensions_and_repeatability(self):
        first = draw_frame(DEMO, 1000)
        second = draw_frame(DEMO, 1000)
        self.assertEqual(first.size, (540, 960))
        self.assertEqual(first.tobytes(), second.tobytes())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "ffmpeg/ffprobe unavailable")
    def test_produces_valid_silent_mp4(self):
        with tempfile.TemporaryDirectory() as directory:
            target = render_demo(Path(directory) / "test.mp4", fps=4)
            self.assertGreater(target.stat().st_size, 1000)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_name,width,height", "-of", "csv=p=0", str(target)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("h264", probe.stdout)
            self.assertIn("540", probe.stdout)
            self.assertIn("960", probe.stdout)

    def test_rejects_invalid_fps(self):
        with self.assertRaises(ValueError):
            render_demo("unused.mp4", fps=0)


if __name__ == "__main__":
    unittest.main()
