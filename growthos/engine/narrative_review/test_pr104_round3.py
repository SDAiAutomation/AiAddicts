"""Tests de REPRODUCTION de la troisième correction (seconde revue Codex, commit 157fc24). N'importent que des symboles déjà présents à 157fc24 :
ils tournent donc contre l'ancien code et y ÉCHOUENT sur l'assertion, pas sur un import.

P0-1 : un texte affiché hors des blocs (racine du script) était ignoré, avec `can_auto_accept=True`.
P0-2 : l'état interne du budget (`settled_usd`, réservations, plafond) pouvait être corrompu puis servir une réservation et un appel fournisseur.
"""
from __future__ import annotations

import copy
import json
import math
import threading
import unittest

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review import snapshot as snap
from growthos.engine.narrative_review.providers import Budget, Prices, ProviderResult
from growthos.engine.narrative_review.reviewer import review
from growthos.engine.narrative_review.test_review import CALLER, PRICES, NetworkBlocked, good_response, run, snapshot_of


def root_script(**extra):
    return {"title": "T", "blocks": [{"role": "hook", "text": "Une phrase claire."}, {"role": "point", "text": "Fin."}], **extra}


class TestP01RootLevelDisplayedText(NetworkBlocked):
    def test_exact_codex_reproduction_root_motion_graphic_is_analysed_and_cannot_be_ignored(self):
        script = root_script(motion_graphic=[{"text": "FAUX TEXTE AFFICHÉ"}])
        before = copy.deepcopy(script)
        s = snap.from_standard(script, organization_id="o", account_id="a", truth_mode="fiction")
        self.assertEqual(script, before)
        overlay = [u for u in s["units"] if u["channel"] == "on_screen"]
        self.assertEqual([(u["text"], u["origin"]["path"]) for u in overlay], [("FAUX TEXTE AFFICHÉ", "/motion_graphic/0/text")])
        self.assertEqual(s["coverage_gaps"], [])
        # un critique qui n'a pas inspecté ce texte ne peut pas faire accepter le script
        skipped = good_response(s)
        overlay_id = overlay[0]["unit_id"]
        for cov in skipped["coverage"]:
            cov["inspected_unit_ids"] = [u for u in cov["inspected_unit_ids"] if u != overlay_id]
        report = run(s, skipped)
        self.assertEqual((report["analysis_status"], report["can_auto_accept"]), ("invalid", False))

    def test_root_motion_graphics_plural_and_nested_forms_are_read(self):
        s = snapshot_of(root_script(motion_graphics=[{"sceneType": "checklist", "title": "Avant", "items": [{"label": "A"}, {"label": "B"}]}]))
        self.assertEqual(sorted(u["text"] for u in s["units"] if u["channel"] == "on_screen"), ["A", "Avant", "B"])
        self.assertEqual(s["coverage_gaps"], [])

    def test_unknown_root_fields_with_content_are_gaps_that_force_review(self):
        for key, value in (("overlay", "TEXTE"), ("caption", {"text": "X"}), ("subtitle", ["a"]), ("description", "Texte publié"),
                           ("badge", 5), ("thumbnail_variants", [{"text": "MINIATURE"}]), ("quiz", {"q": "?"}), ("story", {"shots": [{"dialogue": "Une réplique"}]})):
            s = snapshot_of(root_script(**{key: value}))
            self.assertEqual(s["coverage_gaps"], [f"/{key}"], key)
            report = run(s, good_response(s))   # couverture complète de ce qui a été lu, aucun défaut
            self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False), key)
            self.assertIn("unread_displayed_content", report["reasons"], key)
            self.assertIn(f"unread_content:/{key}", report["limits"], key)

    def test_known_metadata_fields_do_not_create_gaps(self):
        meta = root_script(niche="finance", account="acc", platform="youtube", language="fr", hashtags=["#a"], made_for_kids=False,
                           contentStrategy={"audiencePromise": "x"}, openLoops=[], characters=[{"name": "Ana", "description": "d"}],
                           source_text="brief", generationMetadata={"model": "m"})
        self.assertEqual(snapshot_of(meta)["coverage_gaps"], [])

    def test_unexpected_types_and_malformed_shapes_become_gaps_never_silence_or_crash(self):
        deep = cur = {}
        for _ in range(5000):                         # structure absurdement profonde : aucune RecursionError, une lacune
            cur["x"] = {}
            cur = cur["x"]
        cases = {
            "root motion_graphic string": root_script(motion_graphic="TEXTE"),
            "root motion_graphic number": root_script(motion_graphic=42),
            "root motion_graphic bytes in list": root_script(motion_graphic=[b"raw"]),
            "root motion_graphic deep": root_script(motion_graphic=deep),
            "root unknown deep": root_script(extra=deep),
            "root non-string key": {**root_script(), 7: "TEXTE"},
            "root unknown bytes": root_script(blob=b"xx"),
            "title is a list": {**root_script(), "title": ["T"]},
            "block unknown number": {"title": "T", "blocks": [{"role": "hook", "text": "ok", "badge": 3}]},
            "block mg deep": {"title": "T", "blocks": [{"role": "hook", "text": "ok", "motion_graphic": deep}]},
            "block non-string key": {"title": "T", "blocks": [{"role": "hook", "text": "ok", 9: "TEXTE"}]},
        }
        for label, script in cases.items():
            s = snap.from_standard(script, organization_id="o", account_id="a", truth_mode="fiction")
            self.assertTrue(s["coverage_gaps"], label)
            report = run(s, good_response(s))
            self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False), label)

    def test_hard_malformed_inputs_never_yield_a_snapshot_that_could_be_accepted(self):
        for bad in (None, [], "text", {"blocks": "x"}, {"blocks": [None]}, {"blocks": [{"role": "hook"}]}, {"blocks": [{"text": 5}]}):
            with self.assertRaises(c.ReviewError):
                snap.from_standard(bad, organization_id="o", account_id="a")

    def test_no_coverage_gap_can_ever_coexist_with_auto_accept(self):
        """Propriété : pour toute forme générée avec des lacunes, aucune réponse (même parfaite) ne produit `can_auto_accept=True`."""
        values = ["texte", "", 0, 3.5, True, None, [], {}, [1, "a"], {"a": {"b": ["c"]}}, b"x", ("t",)]
        keys = ["overlay", "caption", "x", "badge", "motion_graphic", "motion_graphics", "description", "hashtags", "source_text"]
        count = 0
        for key in keys:
            for value in values:
                for place in ("root", "block"):
                    script = root_script(**{key: value}) if place == "root" else \
                        {"title": "T", "blocks": [{"role": "hook", "text": "ok", key: value}]}
                    s = snap.from_standard(script, organization_id="o", account_id="a", truth_mode="fiction")
                    report = run(s, good_response(s))
                    if s["coverage_gaps"]:
                        count += 1
                        self.assertFalse(report["can_auto_accept"], (place, key, value))
                        self.assertEqual(report["decision"], "review", (place, key, value))
        self.assertGreater(count, 30)          # la propriété a réellement été exercée

    def test_overlay_text_change_at_root_changes_the_hash(self):
        a = snapshot_of(root_script(motion_graphic=[{"text": "A"}]))
        b = snapshot_of(root_script(motion_graphic=[{"text": "B"}]))
        self.assertNotEqual(a["snapshot_id"], b["snapshot_id"])


class TestP02BudgetStateIntegrity(NetworkBlocked):
    def provider_counter(self, s):
        calls = []
        provider = lambda request: (calls.append(request), ProviderResult(text=json.dumps(good_response(s)), usage={"input": 10, "output": 10}))[1]  # noqa: E731
        return provider, calls

    def corrupted(self, how, value):
        budget = Budget(1.0)
        how(budget, value)
        return budget

    MUTATIONS = {
        "settled_usd": lambda b, v: object.__setattr__(b, "_settled", v),
        "ceiling": lambda b, v: object.__setattr__(b, "_ceiling", v),
        "unknown_calls": lambda b, v: object.__setattr__(b, "_unknown_calls", v),
        "overruns": lambda b, v: object.__setattr__(b, "_overruns", v),
        "reserved_entry": lambda b, v: b._reserved.__setitem__("forged", v),
    }

    def test_exact_codex_reproduction_settled_nan_no_longer_reserves_or_calls_the_provider(self):
        b = Budget(1.0)
        with self.assertRaises((c.ReviewError, AttributeError)):
            b.settled_usd = float("nan")            # l'état n'est plus modifiable par assignation publique
        object.__setattr__(b, "_settled", float("nan"))   # contournement délibéré : l'état est revalidé à chaque opération
        with self.assertRaises(c.ReviewError):
            b.reserve("bypass", 0.0002)
        s = snapshot_of()
        provider, calls = self.provider_counter(s)
        budget = self.corrupted(self.MUTATIONS["settled_usd"], float("nan"))
        report = review(s, provider, caller=CALLER, budget=budget, prices=PRICES, model="m")
        self.assertEqual((calls, report["error"]["code"], report["can_auto_accept"]), ([], c.BUDGET_EXHAUSTED, False))

    def test_every_corrupted_accounting_field_refuses_reservation_and_the_provider_call(self):
        s = snapshot_of()
        nasty = (float("nan"), float("inf"), float("-inf"), -1.0, True, "1", None)
        for name, how in self.MUTATIONS.items():
            for value in nasty:                   # toutes ces valeurs sont invalides pour TOUS les champs (booléens compris)
                provider, calls = self.provider_counter(s)
                budget = self.corrupted(how, value)
                report = review(s, provider, caller=CALLER, budget=budget, prices=PRICES, model="m")
                self.assertEqual(calls, [], (name, value))
                self.assertEqual(report["error"]["code"], c.BUDGET_EXHAUSTED, (name, value))
                self.assertFalse(report["can_auto_accept"], (name, value))
                self.assertIsNotNone(budget.integrity_error(), (name, value))

    def test_inconsistent_but_finite_states_are_refused_too(self):
        b = Budget(1.0)
        object.__setattr__(b, "_reserved", ["not", "a", "dict"])
        with self.assertRaises(c.ReviewError):
            b.reserve("x", 0.1)
        b = Budget(1.0)
        b._reserved[7] = 0.1                       # clé non textuelle
        with self.assertRaises(c.ReviewError):
            b.reserve("x", 0.1)
        b = Budget(1.0)
        b.reserve("a", 0.5)
        with self.assertRaises(c.ReviewError):      # même étiquette : écraserait une réservation existante
            b.reserve("a", 0.1)
        self.assertEqual(b.reserved, {"a": 0.5})

    def test_corruption_between_reservation_and_settlement_poisons_the_budget(self):
        s = snapshot_of()
        budget = Budget(1.0)

        def corrupting(request):
            object.__setattr__(budget, "_settled", float("nan"))           # pendant l'appel fournisseur, après la réservation
            return ProviderResult(text=json.dumps(good_response(s)), usage={"input": 10, "output": 10})
        report = review(s, corrupting, caller=CALLER, budget=budget, prices=PRICES, model="m")
        self.assertIn("budget_state_corrupted", report["limits"])
        self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False))
        self.assertIsNotNone(budget.integrity_error())
        provider, calls = self.provider_counter(s)
        again = review(s, provider, caller=CALLER, budget=budget, prices=PRICES, model="m")
        self.assertEqual((calls, again["error"]["code"]), ([], c.BUDGET_EXHAUSTED))        # il reste refusé, jamais réparé en silence
        object.__setattr__(budget, "_settled", 0.0)                                        # même « remis en état » à la main : empoisonné
        with self.assertRaises(c.ReviewError):
            budget.reserve("late", 0.01)

    def test_reservation_state_is_not_reachable_from_the_outside(self):
        b = Budget(1.0)
        b.reserve("a", 0.3)
        copy_of = b.reserved
        copy_of["a"] = float("nan")                  # muter la copie ne change rien
        copy_of["forged"] = -5.0
        self.assertEqual((b.reserved, b.committed()), ({"a": 0.3}, 0.3))
        for attr in ("settled_usd", "ceiling_usd", "overruns", "unknown_calls", "reserved"):
            with self.assertRaises(AttributeError):
                setattr(b, attr, 1)
        with self.assertRaises(AttributeError):
            b.new_attribute = 1                       # __slots__ : aucun champ ajouté

    def test_atomic_concurrent_reservation_is_preserved_and_a_corruption_race_stays_refused(self):
        budget = Budget(1.0)
        results = []

        def attempt(i):
            try:
                budget.reserve(f"x{i}", 0.3)
                results.append(True)
            except c.ReviewError:
                results.append(False)
        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(16)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(results), 3)            # 3 x 0,3 <= 1,0 < 4 x 0,3
        self.assertTrue(math.isclose(budget.committed(), 0.9))
        object.__setattr__(budget, "_settled", float("inf"))
        with self.assertRaises(c.ReviewError):
            budget.reserve("after", 0.0)

    def test_a_healthy_budget_is_unchanged_in_behaviour(self):
        budget = Budget(1.0)
        budget.reserve("a", 0.4)
        self.assertFalse(budget.settle("a", 0.1))
        self.assertTrue(math.isclose(budget.committed(), 0.1))
        budget.reserve("b", 0.5)
        self.assertTrue(budget.settle("b", 0.9))      # dépassement de la réservation : signalé
        self.assertEqual((budget.overruns, budget.unknown_calls), (1, 0))
        budget.reserve("c", 0.0)
        budget.settle("c", None)
        self.assertEqual(budget.unknown_calls, 1)
        self.assertIsNone(budget.integrity_error())
        Prices(1.0, 1.0)


if __name__ == "__main__":
    unittest.main()
