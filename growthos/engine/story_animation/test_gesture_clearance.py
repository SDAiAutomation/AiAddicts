"""Static guard on the gesture library of the rig_v1 scene: a gesture must not park a hand in front of the speaker's mouth.

Hand targets are written relative to the character's anchors. `neck` is the base of the head, and both heads extend well
below it, so a hand placed near the neck line with a small horizontal offset lands on the chin and the mouth (this is what
hid the lips of Pip and Rosette in the first generated video). The only gestures that put hands near the head on purpose
use a wide offset, to the sides of the face. The full visual check is the gesture gallery (render every gesture, both
characters, close-up), run by hand when the library changes.
"""
import re
import unittest
from pathlib import Path

SCENE = (Path(__file__).resolve().parent / "godot" / "rig_v1" / "scene.gd").read_text(encoding="utf-8")
NEXT_GESTURE = "\n\t\t\""
MIN_SIDE_OFFSET = 120.0  # native px: clear of the face on either side


def gesture_block() -> str:
    start = SCENE.index("func gesture_pose(")
    return SCENE[start:SCENE.index("\nfunc ", start + 1)]


class GestureClearance(unittest.TestCase):
    def test_hands_near_the_neck_stay_to_the_side_of_the_face(self):
        offsets = re.findall(r"neck \+ Vector2\(\s*(-?\d+(?:\.\d+)?)\s*(?:\*\s*dn)?\s*([+-]\s*\d+(?:\.\d+)?\s*\*\s*sin\([^)]*\)\s*\*\s*e)?\s*,\s*(-?\d+(?:\.\d+)?)", gesture_block())
        self.assertTrue(offsets, "expected neck-anchored targets in the gesture library")
        for x, _wiggle, y in offsets:
            self.assertGreaterEqual(abs(float(x)), MIN_SIDE_OFFSET, f"hand at neck offset ({x}, {y}) would cover the face")

    def test_point_leaves_the_free_hand_at_the_belt(self):
        point = gesture_block().split('"point":')[1].split(NEXT_GESTURE)[0]
        free_hand = point.split("arm(P, not right")[1]
        self.assertIn("hip +", free_hand)
        self.assertNotIn("neck +", free_hand)


if __name__ == "__main__":
    unittest.main()
