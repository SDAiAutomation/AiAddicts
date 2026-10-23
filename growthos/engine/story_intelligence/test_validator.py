"""Run: python -m unittest growthos.engine.story_intelligence.test_validator -v"""
import unittest
from copy import deepcopy
from growthos.engine.story_intelligence.validator import validate_storyboard


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.story = {
            "target_duration_s": 10,
            "characters": [{"id": "neo"}, {"id": "orion"}],
            "shots": [
                {"id": "s1", "speaker_id": "neo", "dialogue": "Pourquoi ?", "duration_s": 5},
                {"id": "s2", "speaker_id": "orion", "dialogue": "Écoute.", "duration_s": 5},
            ],
        }

    def test_valid(self):
        self.assertEqual(validate_storyboard(self.story), [])

    def test_unknown_character(self):
        self.story["shots"][0]["speaker_id"] = "unknown"
        self.assertTrue(any("known character" in e for e in validate_storyboard(self.story)))

    def test_empty_dialogue(self):
        self.story["shots"][0]["dialogue"] = " "
        self.assertTrue(any("dialogue" in e for e in validate_storyboard(self.story)))

    def test_duration_mismatch(self):
        self.story["shots"][0]["duration_s"] = 6
        self.assertTrue(any("sum to" in e for e in validate_storyboard(self.story)))

    def test_duplicate_character(self):
        self.story["characters"][1]["id"] = "neo"
        self.assertTrue(any("unique" in e for e in validate_storyboard(self.story)))

    def test_no_mutation(self):
        before = deepcopy(self.story)
        validate_storyboard(self.story)
        self.assertEqual(self.story, before)

    def test_invalid_input(self):
        self.assertTrue(validate_storyboard(None))


if __name__ == "__main__":
    unittest.main()
