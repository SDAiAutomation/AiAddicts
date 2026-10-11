import unittest
from engine.creative_quality_persistence import prepare_report, merge_score_details

class PersistenceTests(unittest.TestCase):
    def test_merge_and_stale_version(self):
        report = dict(schema_version="creative_quality:v1", stage="script", decision="pass",
                      issues=[], enforcement_enabled=False, automatic_edits_applied=False)
        envelope = prepare_report(report, script_version=2)
        merged = merge_score_details({"old": 42}, envelope, current_script_version=2,
                                     current_video_script_version=None)
        self.assertEqual(merged["old"], 42)
        with self.assertRaises(ValueError):
            merge_score_details({}, envelope, current_script_version=3,
                                current_video_script_version=None)

    def test_reject_enforced_report(self):
        report = dict(schema_version="creative_quality:v1", stage="script", decision="pass",
                      issues=[], enforcement_enabled=True, automatic_edits_applied=False)
        with self.assertRaises(ValueError):
            prepare_report(report, script_version=1)

if __name__ == "__main__":
    unittest.main()
