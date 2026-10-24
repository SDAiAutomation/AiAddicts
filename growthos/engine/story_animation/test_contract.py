import json
import os
import unittest
from pathlib import Path
from unittest import mock

from growthos.engine.story_animation import contract

FIXTURE = Path(__file__).parent / "fixtures" / "animation_contract.json"


class AnimationContractFixtureTests(unittest.TestCase):
    """Shared cases: the frontend (growthos-web) must reach the same verdicts."""

    def test_cases(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 30)
        for case in cases:
            with self.subTest(case["name"]):
                errors = contract.validate_animation_story(case["story"], case.get("catalog"))
                self.assertEqual(not errors, case["valid"], errors)

    def test_both_verdicts_are_exercised(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(sum(1 for c in cases if c["valid"]), 3)
        self.assertGreaterEqual(sum(1 for c in cases if not c["valid"]), 25)

    def test_non_finite_numbers_are_rejected(self):
        story = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"][0]["story"]
        story["shots"][0]["camera"]["zoom_to"] = float("inf")
        self.assertTrue(contract.validate_animation_story(story))
        story["shots"][0]["camera"]["zoom_to"] = 1.0
        story["shots"][0]["duration_s"] = float("nan")
        self.assertTrue(contract.validate_animation_story(story))


class RoutingAndFlagTests(unittest.TestCase):
    ANIMATED = {"content_format": "story", "story": {"version": 2}}
    LEGACY_STORY = {"content_format": "story", "story": {"version": 1}}

    def test_flag_is_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(contract.animation_enabled())

    def test_only_explicit_values_enable(self):
        for value, expected in (("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False), ("", False), ("maybe", False)):
            with mock.patch.dict(os.environ, {"STORY_ANIMATION_ENABLED": value}, clear=True):
                self.assertEqual(contract.animation_enabled(), expected, value)

    def test_animated_story_is_refused_when_flag_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(contract.AnimationDisabled):
                contract.route_for(self.ANIMATED)

    def test_animated_story_routes_when_flag_on(self):
        self.assertEqual(contract.route_for(self.ANIMATED, enabled=True), "animated")

    def test_other_scripts_never_change_route(self):
        for script in (self.LEGACY_STORY, {"content_format": "standard"}, {"content_format": "quiz"}, {}, None, [], "x"):
            with self.subTest(script=script):
                self.assertEqual(contract.route_for(script, enabled=True), "legacy")
                self.assertEqual(contract.route_for(script, enabled=False), "legacy")


if __name__ == "__main__":
    unittest.main()
