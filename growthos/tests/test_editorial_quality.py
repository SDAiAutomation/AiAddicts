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


    def test_wide_establishing_shot_hook_is_flagged(self):
        script = {"blocks": [
            {"role": "hook", "text": "3 erreurs qui détruisent ta rétention sans prévenir",
             "visual": "Plan large, rue principale au crépuscule, passants flous."},
        ]}
        report = editorial_quality.analyze_script(script)
        self.assertTrue(any("plan large" in issue for issue in report["issues"]))

    def test_close_up_hook_is_not_flagged(self):
        script = {"blocks": [
            {"role": "hook", "text": "3 erreurs qui détruisent ta rétention sans prévenir",
             "visual": "Gros plan sur deux yeux immenses reflétant la lumière d'un escalier."},
        ]}
        report = editorial_quality.analyze_script(script)
        self.assertFalse(any("plan large" in issue for issue in report["issues"]))

    def test_overlong_title_is_flagged(self):
        script = {"title": "Il a refusé d'aider ce vieil homme… 10 minutes plus tard, il l'a regretté", "blocks": [
            {"role": "hook", "text": "3 erreurs qui détruisent ta rétention sans prévenir"},
        ]}
        report = editorial_quality.analyze_script(script)
        self.assertTrue(any("Titre de" in issue for issue in report["issues"]))
        script["title"] = "La boîte métallique de Bengaluru"
        self.assertFalse(any("Titre de" in issue for issue in editorial_quality.analyze_script(script)["issues"]))


if __name__ == "__main__":
    unittest.main()
