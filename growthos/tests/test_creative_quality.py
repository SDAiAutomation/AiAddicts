import unittest
from engine import creative_quality

class CreativeQualityTests(unittest.TestCase):
    def test_pass(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[]}, editorial_report={"score":100,"issues":[]})
        self.assertEqual(r["decision"],"pass")
        self.assertFalse(r["enforcement_enabled"])

    def test_block(self):
        r = creative_quality.analyze({"blocks":[{"text":"bad sum"}]}, retention_report={"issues":[{"code":"arithmetic_inconsistency","severity":"high","message":"wrong","blocks":[0]}]}, editorial_report={"score":100,"issues":[]})
        self.assertEqual(r["decision"],"block")
        self.assertEqual(r["issues"][0]["evidence"],"bad sum")

    def test_review(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[]}, editorial_report={"score":80,"issues":["Weak hook"]})
        self.assertEqual(r["decision"],"review")

if __name__ == "__main__":
    unittest.main()
