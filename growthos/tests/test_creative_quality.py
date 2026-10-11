import unittest
from engine import creative_quality, editorial_quality

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

    def test_length_only_editorial_issues_are_info_and_do_not_force_review(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[]}, editorial_report={"score":100,"issues":[
            "Titre de 82 caractères (cible : 60 maximum, lisible en entier sur mobile).",
            "CTA trop long (14 mots, cible : 12 maximum)."]})
        self.assertEqual(r["decision"], "pass")
        self.assertEqual({i["severity"] for i in r["issues"]}, {"info"})
        self.assertEqual({i["code"] for i in r["issues"]}, {"editorial_length"})
        self.assertEqual(len(r["issues"]), 2)  # still reported, only less severe

    def test_length_issue_next_to_a_real_issue_still_reviews(self):
        r = creative_quality.analyze({"blocks":[]}, retention_report={"issues":[]}, editorial_report={"score":80,"issues":[
            "Titre de 82 caractères (cible : 60 maximum, lisible en entier sur mobile).",
            "Hook sans élément concret, question ou contraste identifiable."]})
        self.assertEqual(r["decision"], "review")
        by_code = {i["code"]: i["severity"] for i in r["issues"]}
        self.assertEqual(by_code, {"editorial_length": "info", "editorial_heuristic": "warning"})

    def test_length_messages_still_match_editorial_quality(self):
        # Guard against message drift: the prefix match depends on the real messages.
        script = {"title": "T" * 90, "language": "fr", "cta": " ".join(["mot"] * 20),
                  "blocks": [{"role": "hook", "text": "Un hook de cinq mots ici."},
                             {"role": "cta", "text": " ".join(["mot"] * 20)}]}
        editorial = editorial_quality.analyze_script(script)
        messages = [m for m in editorial["issues"] if m.startswith(("Titre de ", "CTA trop long"))]
        self.assertEqual(len(messages), 2, editorial["issues"])
        r = creative_quality.analyze(script, retention_report={"issues": []}, editorial_report=editorial)
        lengths = [i for i in r["issues"] if i["code"] == "editorial_length"]
        self.assertEqual(len(lengths), 2)

if __name__ == "__main__":
    unittest.main()
