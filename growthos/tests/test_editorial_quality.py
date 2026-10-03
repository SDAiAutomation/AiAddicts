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


def _report(language, hook, **extra):
    return editorial_quality.analyze_script({
        "language": language, "title": "Titre court",
        "blocks": [{"role": "hook", "text": hook, "visual": "Gros plan sur l'objet"}, {"role": "cta", "text": "Abonne-toi."}],
        **extra,
    })


def _has_concrete_issue(report):
    return any("sans élément concret" in issue for issue in report["issues"])


class TestHookDetectorIsLanguageAware(unittest.TestCase):
    """Constaté au benchmark du 2026-10-04 : le détecteur ne connaissait que des
    mots français, donc des accroches correctes étaient signalées."""

    def test_a_count_promise_is_concrete_in_every_language(self):
        for language, hook in (
            ("fr", "Trois habitudes qui transforment ta nuit dès ce soir."),
            ("en", "Three habits that change your night starting tonight."),
            ("es", "Tres hábitos que cambian tu noche desde hoy."),
            ("pt", "Três hábitos que mudam a sua noite."),
            ("it", "Tre abitudini che cambiano la tua notte."),
            ("de", "Drei Gewohnheiten, die deine Nacht verändern."),
        ):
            with self.subTest(language=language):
                self.assertFalse(_has_concrete_issue(_report(language, hook)))

    def test_a_proper_noun_or_a_first_claim_is_concrete(self):
        self.assertFalse(_has_concrete_issue(_report("fr", "La toute première photo de la Terre depuis l'espace.")))
        self.assertFalse(_has_concrete_issue(_report("en", "The sun is eight light minutes from Earth.")))

    def test_curiosity_words_work_in_the_script_language(self):
        self.assertFalse(_has_concrete_issue(_report("en", "Nobody tells you this about sleep.")))
        self.assertFalse(_has_concrete_issue(_report("es", "Nunca duermas con el móvil en la cama.")))
        self.assertFalse(_has_concrete_issue(_report("de", "Warum der Himmel blau ist und der Abend rot.")))

    def test_a_flat_statement_is_still_flagged(self):
        self.assertTrue(_has_concrete_issue(_report("fr", "Le ciel est bleu, le coucher s'enflamme de rouge.")))
        self.assertTrue(_has_concrete_issue(_report("en", "The sky is blue and sunsets are red.")))

    def test_a_word_is_matched_whole_not_inside_another_word(self):
        # « mais » ne doit pas être trouvé dans « maison ».
        self.assertTrue(_has_concrete_issue(_report("fr", "Il y a une maison au bord de la mer.")))

    def test_german_capitalised_nouns_are_not_a_proper_noun_signal(self):
        self.assertTrue(_has_concrete_issue(_report("de", "Der Himmel ist blau und der Abend ist rot.")))

    def test_generic_openings_are_detected_per_language(self):
        for language, hook in (("fr", "Voici une vidéo sur la nuit et le repos."), ("en", "Here is a video about sleep and rest today.")):
            with self.subTest(language=language):
                self.assertTrue(any("générique" in issue for issue in _report(language, hook)["issues"]))

    def test_unknown_language_is_lenient_and_default_is_french(self):
        self.assertFalse(_has_concrete_issue(_report("nl", "Three habits that change your night.")))
        self.assertFalse(_has_concrete_issue(editorial_quality.analyze_script({
            "blocks": [{"role": "hook", "text": "Trois habitudes qui transforment ta nuit."}],
        })))

    def test_every_penalty_is_reported_not_only_the_first(self):
        report = _report("fr", "Le ciel est bleu, le coucher s'enflamme de rouge.",
                         title="x" * 70, cta=" ".join(["mot"] * 20))
        self.assertEqual(report["score"], 70)
        self.assertEqual(len(report["issues"]), 3)


if __name__ == "__main__":
    unittest.main()
