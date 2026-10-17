"""Générateurs déterministes de l'Explainer : chiffres exacts, ancres résolues, storyboard valide, pipeline sans aucun appel de modèle."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.explainer import generators, llm, pipeline, schema, timeline  # noqa: E402
from engine.explainer.generators import compound_interest  # noqa: E402

try:
    import playwright  # noqa: F401
    HAVE_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    HAVE_PLAYWRIGHT = False

PARAMS = {"capital": 100, "rate": 10, "years": 10}


class TestNumbers(unittest.TestCase):
    def test_full_precision_totals_match_the_textbook_values(self):
        calc = compound_interest.compute(100, 10, 10)
        self.assertEqual([str(x) for x in calc["totals"][:4]], ["100.00", "110.00", "121.00", "133.10"])
        self.assertEqual(str(calc["totals"][10]), "259.37")   # 100 x 1,1^10 : pas 259,39 (arrondi année par année)
        self.assertEqual(str(calc["simple_total"]), "200.00")

    def test_displayed_additions_always_add_up(self):
        for capital, rate in ((100, 10), (1234.56, 7.3), (50, 3.5), (999, 12.75)):
            calc = compound_interest.compute(capital, rate, 6)
            for k, g in enumerate(calc["gains"]):
                self.assertEqual(calc["totals"][k] + g, calc["totals"][k + 1])

    def test_invalid_parameters_are_refused(self):
        for bad in ({"capital": 0, "rate": 10, "years": 10}, {"capital": 100, "rate": 99, "years": 10}, {"capital": 100, "rate": 10, "years": 2},
                    {"capital": "abc", "rate": 10, "years": 10}, {"rate": 10, "years": 10}, {**PARAMS, "currency": "gbp"}):
            with self.assertRaises(ValueError):
                generators.build("compound_interest", bad)
        with self.assertRaises(ValueError):
            generators.build("compound_interest", PARAMS, lang="xx")
        with self.assertRaises(ValueError):
            generators.build("inconnu", PARAMS)


class TestSpec(unittest.TestCase):
    def test_every_language_and_rate_gives_a_valid_storyboard_with_resolvable_anchors(self):
        for lang in ("fr", "en"):
            for params in (PARAMS, {"capital": 1234.56, "rate": 7.3, "years": 15, "currency": "usd"}, {"capital": 50, "rate": 3.5, "years": 8}):
                spec = generators.build("compound_interest", params, lang)
                self.assertEqual(schema.validate_storyboard(spec["storyboard"], len(spec["lines"])), [], (lang, params))
                narration, words = timeline.estimate_narration(spec["lines"])
                total = timeline.total_duration(narration, words)
                for plan, window in zip(spec["storyboard"]["plans"], timeline.plan_windows(spec["storyboard"], narration, total)):
                    _, unresolved = timeline.resolve_anchors(plan, window, words)
                    self.assertEqual(unresolved, [], (lang, params, plan["id"]))
                self.assertEqual([p["id"] for p in spec["composition"]["plans"]], [p["id"] for p in spec["storyboard"]["plans"]])

    def test_every_number_on_screen_comes_from_the_calculation(self):
        spec = generators.build("compound_interest", PARAMS, "fr")
        text = " ".join(spec["lines"])
        for expected in ("100 euros", "110 euros", "121 euros", "12,10 euros", "133,10 euros", "259,37 euros", "200 euros"):
            self.assertIn(expected, text)
        self.assertIn("10 % par an", text)
        self.assertEqual(spec["composition"]["plans"][5]["params"]["values"][-1], 259.37)

    def test_english_uses_decimal_points_and_no_french_text(self):
        spec = generators.build("compound_interest", PARAMS, "en")
        text = " ".join(spec["lines"])
        self.assertIn("133.10 euros", text)
        self.assertNotIn("euros à", text)


@unittest.skipUnless(HAVE_PLAYWRIGHT, "playwright non installé")
class TestPipelineWithoutModel(unittest.TestCase):
    def test_all_plans_validate_and_no_model_is_called(self):
        def forbidden(*a, **k):
            raise AssertionError("aucun appel de modèle n'est permis avec un générateur déterministe")

        for lang in ("fr", "en"):
            spec = generators.build("compound_interest", PARAMS, lang)
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(llm, "complete", forbidden):
                report = pipeline.generate(spec["topic"], tmp, spec=spec, do_render=False, use_critic=False, log=lambda *_: None)
            self.assertEqual(report["fallbacks"], [], (lang, [(p["id"], p["history"][-1]["errors"]) for p in report["plans"] if not p["ok"]]))
            self.assertEqual(report["mode"], "templates")
            self.assertEqual(report["spend"]["totalUsd"], 0)
            self.assertNotIn("factCheck", report)


if __name__ == "__main__":
    unittest.main()
