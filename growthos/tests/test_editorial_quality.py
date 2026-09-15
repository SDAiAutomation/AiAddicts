import unittest

from engine import editorial_quality


class TestEditorialQuality(unittest.TestCase):
    def test_specific_hook_and_short_cta_score_well(self):
        script = {"blocks": [
            {"role": "hook", "text": "3 erreurs qui détruisent ta rétention sans prévenir"},
            {"role": "cta", "text": "Abonne-toi pour la suite."},
        ]}
        report = editorial_quality.analyze_script(script)
        self.assertGreaterEqual(report["score"], 80)
        self.assertEqual(report["issues"], [])

    def test_generic_hook_is_flagged(self):
        script = {"blocks": [
            {"role": "hook", "text": "Tu veux améliorer ton business dès maintenant"},
        ]}
        report = editorial_quality.analyze_script(script)
        self.assertLess(report["score"], 80)
        self.assertTrue(any("générique" in issue for issue in report["issues"]))

    def test_long_hook_and_cta_are_flagged(self):
        script = {
            "cta": "Clique sur le lien dans ma bio et rejoins notre programme complet pour tout apprendre dès maintenant",
            "blocks": [{"role": "hook", "text": " ".join(["mot"] * 20)}],
        }
        report = editorial_quality.analyze_script(script)
        self.assertTrue(any("Hook trop long" in issue for issue in report["issues"]))
        self.assertTrue(any("CTA trop long" in issue for issue in report["issues"]))


if __name__ == "__main__":
    unittest.main()
