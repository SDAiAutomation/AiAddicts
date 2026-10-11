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

    def test_filtered_blocks_preserve_index(self):
        r = creative_quality.analyze({"blocks":[None, {"role":"hook","text":"Actual hook"}]}, retention_report={"issues":[{"code":"role_label_leak","blocks":[0],"message":"leak"}]}, editorial_report={"score":100,"issues":[]})
        self.assertEqual(r["issues"][0]["evidence"], "Actual hook")

    def test_invalid_index_not_reported_as_valid(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[{"code":"viewer_placeholder","blocks":[99],"message":"missing"}]}, editorial_report={"score":100,"issues":[]})
        self.assertIsNone(r["issues"][0]["block_index"])

    def test_combine_keeps_enforcement_disabled(self):
        script = {"stage":"script","decision":"pass","issues":[]}
        render = {"stage":"render","decision":"block","issues":[{"code":"audio_stream_missing"}]}
        combined = creative_quality.combine(script, render)
        self.assertEqual(combined["decision"], "block")
        self.assertFalse(combined["enforcement_enabled"])
        self.assertEqual(combined["stages_checked"], ["script", "render"])

    def test_review(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[]}, editorial_report={"score":80,"issues":["Weak hook"]})
        self.assertEqual(r["decision"],"review")

if __name__ == "__main__":
    unittest.main()
