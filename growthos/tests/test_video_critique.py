import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import video_critique as vc

OK = {"scores": {k: 7 for k in vc.CRITERIA}, "worst": [{"criterion": "hook", "frame": 1, "issue": "x"}] * 5}


class ParseTest(unittest.TestCase):
    def test_valid_clamped_and_worst_capped(self):
        raw = {"scores": {**OK["scores"], "hook": 99}, "worst": OK["worst"]}
        res = vc.parse(raw)
        self.assertEqual(res["scores"]["hook"], 10)
        self.assertEqual(len(res["worst"]), 3)

    def test_missing_criterion_is_none(self):
        self.assertIsNone(vc.parse({"scores": {"hook": 5}}))
        self.assertIsNone(vc.parse("nope"))
