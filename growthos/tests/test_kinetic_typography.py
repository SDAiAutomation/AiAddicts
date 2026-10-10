import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import kinetic_typography


class TestExtractEmphasisNumber(unittest.TestCase):
    def test_currency_before_amount(self):
        self.assertEqual(kinetic_typography.extract_emphasis_number("Si tu economises $10 par jour."), "$10")

    def test_currency_after_amount(self):
        self.assertEqual(kinetic_typography.extract_emphasis_number("Le prix est de 120$ ce mois-ci."), "120$")

    def test_percentage(self):
        self.assertEqual(kinetic_typography.extract_emphasis_number("Cela represente 45% de votre revenu."), "45%")

    def test_grouped_number_without_symbol(self):
        self.assertEqual(kinetic_typography.extract_emphasis_number("Il a economise 3,650 en un an."), "3,650")

    def test_first_match_wins(self):
        text = "Si tu economises $10 par jour, ca fait $3,650 par an."
        self.assertEqual(kinetic_typography.extract_emphasis_number(text), "$10")

    def test_bare_number_is_not_matched(self):
        # Un nombre nu (sans devise ni regroupement) est trop bruyant pour une
        # mise en avant : dates, heures, comptages ne doivent pas déclencher.
        self.assertIsNone(kinetic_typography.extract_emphasis_number("Il etait 3 heures du matin."))
        self.assertIsNone(kinetic_typography.extract_emphasis_number("Trois amis se retrouvent."))

    def test_no_number_returns_none(self):
        self.assertIsNone(kinetic_typography.extract_emphasis_number("Aucun chiffre ici."))

    def test_empty_text_returns_none(self):
        self.assertIsNone(kinetic_typography.extract_emphasis_number(""))
        self.assertIsNone(kinetic_typography.extract_emphasis_number(None))


class TestDeriveEmphasisPhrase(unittest.TestCase):
    def test_takes_the_last_clause_french(self):
        text = "Nour trouva une boite a musique cassee, oubliee depuis des annees."
        self.assertEqual(kinetic_typography.derive_emphasis_phrase(text), "OUBLIEE DEPUIS DES ANNEES")

    def test_takes_the_last_clause_english(self):
        text = "Your raise didn't vanish, your spending grew to meet it."
        self.assertEqual(kinetic_typography.derive_emphasis_phrase(text), "GREW TO MEET IT")

    def test_leading_link_word_is_dropped(self):
        text = "Aurais-tu ouvert la boite tout de suite, ou attendu le bon moment ?"
        self.assertEqual(kinetic_typography.derive_emphasis_phrase(text), "ATTENDU LE BON MOMENT")

    def test_never_starts_on_a_function_word(self):
        text = "Le grenier abandonne ou elle vivait etait rempli de vieux souvenirs silencieux."
        self.assertEqual(kinetic_typography.derive_emphasis_phrase(text), "VIEUX SOUVENIRS SILENCIEUX")

    def test_elided_function_word_is_not_a_content_word(self):
        # "qu'elle n'avait" sont des mots vides ; "l'interieur" garde son nom.
        text = "A l'interieur, une petite photo montrait une famille de renards qu'elle n'avait jamais vue."
        self.assertEqual(kinetic_typography.derive_emphasis_phrase(text), "JAMAIS VUE")

    def test_a_whole_short_sentence_is_not_repeated_as_kinetic_text(self):
        self.assertIsNone(kinetic_typography.derive_emphasis_phrase("Rule #3 is next."))
        self.assertIsNone(kinetic_typography.derive_emphasis_phrase("Save first."))

    def test_phrase_is_a_strict_sub_span_of_the_narration(self):
        text = "Une manivelle rouillee refusait de tourner, bloquee depuis trop longtemps."
        phrase = kinetic_typography.derive_emphasis_phrase(text)
        self.assertIn(phrase.lower(), text.lower())
        self.assertLess(len(phrase), len(text.rstrip(".")))

    def test_no_mid_word_truncation_and_bounded_length(self):
        text = " ".join(f"mot{i}" for i in range(50)) + "."
        phrase = kinetic_typography.derive_emphasis_phrase(text)
        self.assertLessEqual(len(phrase.split()), 4)
        for word in phrase.lower().split():
            self.assertIn(word, text.split() + [w.rstrip(".") for w in text.split()])

    def test_empty_text_returns_none(self):
        self.assertIsNone(kinetic_typography.derive_emphasis_phrase(""))
        self.assertIsNone(kinetic_typography.derive_emphasis_phrase(None))

    def test_image_direction_is_never_shown_to_the_viewer(self):
        # `visual` est une consigne d'image : il ne devient jamais du texte à l'écran.
        scene = kinetic_typography.build_emphasis_scene({"visual": "Gros plan sur economiser d'abord.", "text": ""})
        self.assertIsNone(scene)


class TestBuildEmphasisScene(unittest.TestCase):
    def test_scene_carries_the_exact_extracted_value_from_visual(self):
        scene = kinetic_typography.build_emphasis_scene({"visual": "Cela fait $3,650 par an.", "text": ""})
        self.assertEqual(scene, {"sceneType": "big_number", "displayValue": "$3,650"})

    def test_number_only_in_narration_is_still_detected(self):
        # Correctif Phase 2.6 : un `visual` peuplé mais sans chiffre ne doit
        # plus masquer un chiffre présent uniquement dans la narration.
        block = {"visual": "Montrer l'argent mis de cote.", "text": "Mets $600 de cote immediatement."}
        scene = kinetic_typography.build_emphasis_scene(block)
        self.assertEqual(scene, {"sceneType": "big_number", "displayValue": "$600"})

    def test_visual_number_wins_over_narration_number(self):
        block = {"visual": "Ecran affichant $2,400 de solde.", "text": "Il reste $600 ce mois-ci."}
        scene = kinetic_typography.build_emphasis_scene(block)
        self.assertEqual(scene["displayValue"], "$2,400")

    def test_explicit_motion_graphic_takes_priority_over_extraction(self):
        motion = {"sceneType": "formula", "terms": ["REVENU", "= BUDGET"]}
        block = {"visual": "Contient $999 quelque part.", "text": "", "motion_graphic": motion}
        scene = kinetic_typography.build_emphasis_scene(block)
        self.assertEqual(scene, motion)

    def test_invalid_motion_graphic_falls_through_to_extraction(self):
        block = {"visual": "$50 sur la table.", "text": "", "motion_graphic": {"sceneType": "not_a_real_type"}}
        scene = kinetic_typography.build_emphasis_scene(block)
        self.assertEqual(scene, {"sceneType": "big_number", "displayValue": "$50"})

    def test_no_number_falls_back_to_a_derived_phrase_instead_of_blank(self):
        # Correctif Phase 2.6 (section 3) : un bloc sans chiffre n'est plus
        # nécessairement vide — il reçoit une courte phrase déterministe.
        block = {"visual": "", "text": "Economiser devrait se faire avant tout, pas apres avoir depense."}
        scene = kinetic_typography.build_emphasis_scene(block)
        self.assertEqual(scene["sceneType"], "icon_text")
        self.assertEqual(scene["text"], "APRES AVOIR DEPENSE")

    def test_scene_never_invents_a_label(self):
        scene = kinetic_typography.build_emphasis_scene({"visual": "45% de reussite.", "text": ""})
        self.assertNotIn("title", scene)
        self.assertNotIn("label", scene)

    def test_completely_empty_block_returns_none(self):
        self.assertIsNone(kinetic_typography.build_emphasis_scene({"visual": "", "text": ""}))
        self.assertIsNone(kinetic_typography.build_emphasis_scene({}))


if __name__ == "__main__":
    unittest.main()
