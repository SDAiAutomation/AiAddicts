import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import trim


class BuildTrimArgs(unittest.TestCase):
    def test_start_and_end(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 2.0, 10.0)
        # -ss placé AVANT -i (seek rapide)
        self.assertLess(args.index("-ss"), args.index("-i"))
        self.assertEqual(args[args.index("-ss") + 1], "2.000")
        # -t = durée = end - start
        self.assertEqual(args[args.index("-t") + 1], "8.000")
        self.assertEqual(args[-1], "out.mp4")

    def test_start_only_has_no_duration_bound(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 3.5, None)
        self.assertIn("-ss", args)
        self.assertNotIn("-t", args)

    def test_end_only_has_no_seek(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 0.0, 12.0)
        self.assertNotIn("-ss", args)
        self.assertEqual(args[args.index("-t") + 1], "12.000")

    def test_duration_never_below_minimum(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 5.0, 5.1)
        self.assertEqual(args[args.index("-t") + 1], f"{trim._MIN_CLIP_S:.3f}")

    def test_reencodes_with_faststart(self):
        args = trim.build_trim_args("in.mp4", "out.mp4", 1.0, 2.0)
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")
        self.assertEqual(args[args.index("-c:a") + 1], "aac")
        self.assertIn("+faststart", args)


class Bust(unittest.TestCase):
    def test_appends_query_when_none(self):
        self.assertRegex(trim._bust("https://x/a.mp4"), r"^https://x/a\.mp4\?t=\d+$")

    def test_appends_with_ampersand_when_query_present(self):
        self.assertRegex(trim._bust("https://x/a.mp4?foo=1"), r"\?foo=1&t=\d+$")


if __name__ == "__main__":
    unittest.main()
