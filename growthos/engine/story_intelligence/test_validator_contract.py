import json
import unittest
from pathlib import Path

from growthos.engine.story_intelligence.validator import validate_storyboard

FIXTURE = Path(__file__).parent / "fixtures" / "validator_contract.json"


class ValidatorContractTests(unittest.TestCase):
    """Cas partagés avec le frontend (growthos-web) : la validation locale de Story Studio doit rester alignée."""

    def test_cases(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            with self.subTest(case["name"]):
                errors = validate_storyboard(case["story"])
                self.assertEqual(not errors, case["valid"], errors)


if __name__ == "__main__":
    unittest.main()
