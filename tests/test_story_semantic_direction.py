"""Offline checks for conservative intent-based shot planning."""
import unittest

from growthos.engine.story_animation.semantic_direction import direction
from growthos.engine.story_animation.shotplan import narrated_beats


class SemanticDirectionTests(unittest.TestCase):
    def test_no_intent_keeps_legacy(self):
        self.assertIsNone(direction("", [], "narrator"))

    def test_object_requires_existing_asset(self):
        self.assertIsNone(direction("Open the book", [{"props": []}], "pip"))
        self.assertEqual(direction("Look at the clock", [{"props": ["alarm_clock"]}], "pip")["shot_type"], "insert")

    def test_reveal_uses_supported_composition(self):
        self.assertEqual(direction("Discover the truth", [{"props": []}], "pip")["shot_type"], "close_up")
        self.assertEqual(direction("Reveal the secret", [{"props": []}], "narrator")["shot_type"], "medium")

    def test_narrated_beats_preserve_timing(self):
        entry = {
            "start": 0.0, "end": 12.0, "speaker": "narrator",
            "actors": [{"role": "pip", "gesture": "idle", "mood": "neutral", "props": []}],
            "shot_type": "wide", "camera": {"move": "static", "zoom_from": 1.0, "zoom_to": 1.0},
            "transition_in": "cut", "intent": "Discover the truth",
        }
        beats = narrated_beats(entry, 0)
        self.assertGreater(len(beats), 1)
        self.assertEqual(beats[0]["shot_type"], "medium")
        self.assertEqual(beats[0]["start"], 0.0)
        self.assertEqual(beats[-1]["end"], 12.0)
        self.assertFalse(any(beat.get("empty") for beat in beats))


if __name__ == "__main__":
    unittest.main()
