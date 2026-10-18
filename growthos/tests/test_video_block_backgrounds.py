import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import video


class BlockBackgroundTests(unittest.TestCase):
    def _render(self, bg_colors):
        used = []

        def fake_clip(image_path, duration, out_path, resolution, bg_color, fps, **_kwargs):
            used.append((Path(out_path).name, bg_color))
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"clip")
            return out_path

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(video, "_render_block_clip", fake_clip), mock.patch.object(video, "_run"):
            video.render_final(str(Path(folder) / "a.wav"), str(Path(folder) / "c.ass"), str(Path(folder) / "o.mp4"),
                               [2.0, 2.0, 2.0], bg_colors=bg_colors)
        return [colour for _, colour in sorted(used)]  # les plans sont rendus en parallèle

    def test_each_block_can_have_its_own_base_colour(self):
        self.assertEqual(self._render(["0x111111", "0x222222", "0x333333"]), ["0x111111", "0x222222", "0x333333"])

    def test_blocks_without_a_colour_use_the_default(self):
        self.assertEqual(self._render([None, "0x222222"]), [video.DEFAULT_BG, "0x222222", video.DEFAULT_BG])
        self.assertEqual(self._render(None), [video.DEFAULT_BG] * 3)


if __name__ == "__main__":
    unittest.main()
