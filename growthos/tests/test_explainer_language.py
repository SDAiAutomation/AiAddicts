"""La langue du script atteint les consignes de l'Explainer : les textes affichés (titres, bulles du guide) suivent la narration.

Les consignes et les exemples de l'Explainer sont en français (« Salut ! », Awa, Léa) ; sans note de langue, un modèle peut les
recopier dans une vidéo dont la voix est dans une autre langue."""
import importlib
import json
import tempfile
import unittest
from pathlib import Path

from engine.explainer import director, integration, prompts

from tests.test_explainer_integration import fake_pipeline, script


def optional(name):
    try:
        return importlib.import_module(f"engine.explainer.{name}")
    except ImportError:   # esprima absent : composer et animator importent le validateur
        return None


NARRATION = [(0.0, "You invest 100 dollars."), (2.0, "It grows every year.")]


class LanguageNoteTests(unittest.TestCase):
    def test_note_names_the_language_and_forbids_copying_the_french_examples(self):
        note = prompts.language_note("en")
        self.assertIn("English (en)", note)
        self.assertIn("bulles du guide", note)
        self.assertIn("ne les recopie jamais", note)

    def test_unknown_code_is_named_as_is_not_hidden(self):
        self.assertIn("xx", prompts.language_note("xx"))


class DirectorBriefTests(unittest.TestCase):
    def test_english_brief_carries_the_note(self):
        self.assertIn("LANGUE DE LA VIDÉO : English", director.narration_brief("Compound interest", NARRATION, "en"))

    def test_french_brief_is_unchanged(self):
        self.assertEqual(director.narration_brief("Sujet", NARRATION), director.narration_brief("Sujet", NARRATION, "fr"))
        self.assertNotIn("LANGUE DE LA VIDÉO", director.narration_brief("Sujet", NARRATION, "fr"))


class ComposerAnimatorBriefTests(unittest.TestCase):
    def test_composer_and_animator_briefs_follow_the_language(self):
        composer, animator = optional("composer"), optional("animator")
        if composer is None or animator is None:
            self.skipTest("esprima absent")
        storyboard = {"world": {}, "plans": [{"id": "p1", "lines": [0], "intent": "x", "visual": "y", "anchors": []}]}
        windows = [{"duration": 3.0}]
        anchors = {"p1": {}}
        en = json.loads(composer.brief(storyboard, windows, anchors, NARRATION, "Topic", "en"))
        fr = json.loads(composer.brief(storyboard, windows, anchors, NARRATION, "Topic", "fr"))
        self.assertIn("English (en)", en["langue"])
        self.assertNotIn("langue", fr)
        plan = {"id": "p1", "intent": "x", "visual": "y", "camera": "c", "anchors": []}
        self.assertIn("English (en)", json.loads(animator.plan_brief(plan, 3.0, {}, "text", "Topic", {}, {}, "en"))["langue"])
        self.assertNotIn("langue", json.loads(animator.plan_brief(plan, 3.0, {}, "text", "Topic", {}, {})))


class IntegrationLanguageTests(unittest.TestCase):
    def _run(self, **extra):
        calls = []
        words = [[{"text": "a", "start": 0.0, "end": 0.5}] for _ in range(3)]
        with tempfile.TemporaryDirectory() as folder:
            integration.generate_clips(script(**extra), [1.0, 1.0, 1.0], words, Path(folder), generate_fn=fake_pipeline(calls).generate, log=lambda *_: None)
        return calls[0]

    def test_script_language_reaches_the_pipeline(self):
        self.assertEqual(self._run(language="en")["language"], "en")

    def test_missing_language_keeps_the_french_default(self):
        self.assertEqual(self._run()["language"], "fr")

    def test_language_changes_the_reuse_key(self):
        words = {"words": [{"word": "a"}]}
        self.assertNotEqual(integration._inputs_hash(["x"], words, "templates", False, "fr"), integration._inputs_hash(["x"], words, "templates", False, "en"))


if __name__ == "__main__":
    unittest.main()
