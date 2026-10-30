"""Tests de REPRODUCTION des trois blocages P0 de la revue Codex de la PR #104 (commit 7b6d0cc). Chacun échouait avant le correctif.

1. Standard : du texte affiché (motion_graphic, champs de bloc) pouvait être ignoré avec `can_auto_accept: true`.
2. Budget : NaN, +-inf et négatifs contournaient la réservation.
3. Runner : un fournisseur callable arbitraire pouvait ouvrir le réseau. Ici, des tentatives RÉELLES (sur la boucle locale, vers un
   serveur d'écoute du test) prouvent le blocage ; un témoin hors campagne prouve que la connexion aboutirait sans la garde.
"""
from __future__ import annotations

import copy
import json
import math
import socket
import types
import unittest
from unittest import mock

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review import snapshot as snap
from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import runner
from growthos.engine.narrative_review.harness.offline import OfflineProvider, OfflineViolation, network_denied, offline
from growthos.engine.narrative_review.harness.simulation import simulated_critic, simulated_generator
from growthos.engine.narrative_review.providers import (Budget, Prices, ProviderResult, estimate_usd, finite_nonneg, max_call_usd)
from growthos.engine.narrative_review.reviewer import Caller, review
from growthos.engine.narrative_review.test_review import (ACC, CALLER, ORG, PRICES, anchor, finding, good_response, provider_of, run,
                                                          snapshot_of)


def script_with(block_extra=None):
    return {"title": "La file", "blocks": [{"role": "hook", "text": "Une file grandit.", **(block_extra or {})},
                                           {"role": "point", "text": "Un homme demande pourquoi."}]}


class TestBlock1StandardDisplayedText(unittest.TestCase):
    """Reproduction exacte de la revue : motion_graphic=[{"text": "FAUX TEXTE AFFICHÉ"}] ignoré, décision `accept`."""

    def setUp(self):
        self.script = script_with({"motion_graphic": [{"text": "FAUX TEXTE AFFICHÉ"}]})
        self.snap = snapshot_of(self.script)

    def test_the_overlay_text_is_now_an_analysed_unit_with_provenance(self):
        overlay = [u for u in self.snap["units"] if u["channel"] == "on_screen"]
        self.assertEqual([u["text"] for u in overlay], ["FAUX TEXTE AFFICHÉ"])
        self.assertEqual(overlay[0]["origin"]["path"], "/blocks/0/motion_graphic/0/text")
        self.assertEqual(self.snap["coverage_gaps"], [])
        self.assertNotIn("standard_on_screen_text_not_read", run(self.snap, good_response(self.snap))["limits"])

    def test_a_critic_that_skipped_the_overlay_cannot_auto_accept(self):
        skipped = good_response(self.snap)
        overlay_id = next(u["unit_id"] for u in self.snap["units"] if u["channel"] == "on_screen")
        for cov in skipped["coverage"]:
            cov["inspected_unit_ids"] = [u for u in cov["inspected_unit_ids"] if u != overlay_id]
        report = run(self.snap, skipped)
        self.assertEqual((report["analysis_status"], report["can_auto_accept"], report["decision"]), ("invalid", False, "review"))
        self.assertEqual(report["error"]["code"], c.INCOMPLETE_COVERAGE)

    def test_a_critic_that_inspected_everything_can_accept_and_can_anchor_on_the_overlay(self):
        report = run(self.snap, good_response(self.snap))
        self.assertEqual((report["decision"], report["can_auto_accept"]), ("accept", True))
        overlay_id = next(u["unit_id"] for u in self.snap["units"] if u["channel"] == "on_screen")
        f = finding("TRUTH_MODE_MISMATCH", anchors=[anchor(overlay_id, "FAUX TEXTE", 0)], inspected_unit_ids=[overlay_id])
        self.assertEqual(run(self.snap, good_response(self.snap, findings=[f]))["decision"], "revise")

    def test_every_viewer_text_shape_of_motion_graphic_is_read(self):
        shapes = [
            {"sceneType": "icon_text", "displayText": "Les petits achats", "icon": "coin"},
            {"sceneType": "checklist", "title": "Avant d'acheter", "items": [{"label": "Attendre 24 h"}, {"label": "Comparer"}]},
            {"sceneType": "comparison", "optionA": {"label": "Offre A", "value": 6}, "optionB": {"label": "Offre B", "value": 2}},
            {"sceneType": "big_number", "value": 150, "displayValue": "150 EUR par mois", "label": "Il reste"},
            {"sceneType": "equation_steps", "steps": [{"text": "1000 - 850", "spoken": "mille moins huit cent cinquante"}]},
        ]
        wanted = [["Les petits achats"], ["Avant d'acheter", "Attendre 24 h", "Comparer"], ["Offre A", "6", "Offre B", "2"],
                  ["150", "150 EUR par mois", "Il reste"], ["1000 - 850"]]
        for shape, expected in zip(shapes, wanted):
            s = snapshot_of(script_with({"motion_graphic": shape}))
            overlay = [u["text"] for u in s["units"] if u["channel"] == "on_screen"]
            self.assertEqual(sorted(overlay), sorted(expected), shape["sceneType"])
            self.assertEqual(s["coverage_gaps"], [])
            self.assertNotIn("mille moins", json.dumps(overlay))  # l'ancre de narration n'est pas un texte affiché

    def test_unknown_block_field_with_text_is_a_coverage_gap_and_forces_review(self):
        s = snapshot_of(script_with({"caption_overlay": "TEXTE QUE L'ADAPTATEUR NE SAIT PAS LIRE"}))
        self.assertEqual(s["coverage_gaps"], ["/blocks/0/caption_overlay"])
        report = run(s, good_response(s))   # couverture COMPLÈTE de ce qui a été lu, aucun défaut
        self.assertEqual((report["decision"], report["can_auto_accept"]), ("review", False))
        self.assertIn("unread_displayed_content", report["reasons"])
        self.assertIn("unread_content:/blocks/0/caption_overlay", report["limits"])

    def test_non_text_motion_graphic_forms_are_gaps_not_silence(self):
        for odd in ("FAUX TEXTE", 42, True):
            s = snapshot_of(script_with({"motion_graphic": odd}))
            self.assertEqual(s["coverage_gaps"], ["/blocks/0/motion_graphic"], repr(odd))
            self.assertEqual(run(s, good_response(s))["can_auto_accept"], False)

    def test_known_non_viewer_fields_are_not_gaps_and_changed_overlay_text_changes_the_hash(self):
        s = snapshot_of(script_with({"visual": "Gros plan", "shotType": "close_up", "voice_id": "v", "retentionRole": "hook"}))
        self.assertEqual(s["coverage_gaps"], [])
        other = snapshot_of(script_with({"motion_graphic": [{"text": "AUTRE TEXTE"}]}))
        self.assertNotEqual(other["snapshot_id"], self.snap["snapshot_id"])

    def test_reading_still_never_mutates_the_script(self):
        before = copy.deepcopy(self.script)
        snapshot_of(self.script)
        self.assertEqual(self.script, before)


class TestBlock2NonFiniteMoney(unittest.TestCase):
    BAD = (float("nan"), float("inf"), float("-inf"), -0.01, -1, True, "1", None)

    def test_prices_and_ceiling_are_refused_at_construction(self):
        for bad in self.BAD:
            with self.assertRaises(c.ReviewError, msg=repr(bad)) as ctx:
                Prices(input_per_m=bad, output_per_m=2.0)
            self.assertEqual(ctx.exception.code, c.BUDGET_EXHAUSTED)
            with self.assertRaises(c.ReviewError):
                Prices(input_per_m=1.0, output_per_m=bad)
            with self.assertRaises(c.ReviewError):
                Budget(bad)
        with self.assertRaises(c.ReviewError):
            Prices(1.0, 2.0, currency=" ")
        Budget(0.0)
        Prices(0.0, 0.0)  # zéro est une valeur légitime et explicite

    def test_reservation_refuses_non_finite_and_negative_amounts_and_holds_the_boundary(self):
        budget = Budget(1.0)
        for bad in (float("nan"), float("inf"), float("-inf"), -1.0, None):
            with self.assertRaises(c.ReviewError, msg=repr(bad)):
                budget.reserve("x", bad)
        self.assertEqual((budget.committed(), budget.reserved), (0.0, {}))
        budget.reserve("a", 0.4)
        budget.reserve("b", 0.6)                      # exactement le plafond : accepté
        with self.assertRaises(c.ReviewError):
            budget.reserve("c", 1e-6)                 # au-dessus : refusé
        self.assertTrue(math.isfinite(budget.committed()))

    def test_a_price_object_that_bypasses_validation_still_yields_no_cost_and_no_call(self):
        forged = Prices(1.0, 2.0)
        object.__setattr__(forged, "input_per_m", float("nan"))            # contournement de la dataclass figée
        duck = types.SimpleNamespace(input_per_m=float("inf"), output_per_m=2.0, currency="USD")
        for prices in (forged, duck, types.SimpleNamespace(input_per_m=-1.0, output_per_m=1.0)):
            self.assertIsNone(max_call_usd(prices, 16_000, 4_000))
            self.assertIsNone(estimate_usd({"input": 10, "output": 10}, prices))
            s, calls, budget = snapshot_of(), [], Budget(10.0)
            report = run(s, good_response(s), prices=prices, budget=budget, calls=calls)
            self.assertEqual((calls, report["error"]["code"], budget.committed()), ([], c.BUDGET_EXHAUSTED, 0.0))

    def test_caps_and_usage_are_validated_before_any_arithmetic(self):
        for bad in (float("nan"), float("inf"), -1):
            self.assertIsNone(max_call_usd(PRICES, bad, 4_000))
            self.assertIsNone(max_call_usd(PRICES, 16_000, bad))
            self.assertIsNone(estimate_usd({"input": bad, "output": 1}, PRICES))
            self.assertIsNone(estimate_usd({"input": 1, "output": bad}, PRICES))
        self.assertIsNone(max_call_usd(PRICES, 10**400, 4_000) if False else max_call_usd(PRICES, 1e308, 1e308))  # débordement -> non fini

    def test_invalid_usage_from_the_provider_keeps_the_reservation_and_is_never_zero(self):
        s = snapshot_of()
        for usage in ({"input": float("nan"), "output": 5}, {"input": float("inf"), "output": 5}, {"input": -5, "output": 5}):
            budget = Budget(1.0)
            provider = lambda request, u=usage: ProviderResult(text=json.dumps(good_response(s)), usage=u)  # noqa: E731
            report = review(s, provider, caller=CALLER, budget=budget, prices=PRICES, model="m")
            self.assertIsNone(report["usage"]["estimated_cost"])
            self.assertTrue(math.isfinite(budget.committed()) and budget.committed() > 0)   # inconnu = réservation conservée, pas 0
            self.assertEqual(budget.unknown_calls, 1)

    def test_the_runner_makes_zero_provider_calls_with_invalid_money(self):
        forged = Prices(1.0, 2.0)
        object.__setattr__(forged, "output_per_m", float("nan"))
        gen, crit = simulated_generator(), simulated_critic()
        result = runner.run_campaign(corp.load_corpus(), generator=gen, critic=crit, budget=Budget(5.0), gen_prices=forged,
                                     critic_prices=forged, gen_model="g", critic_model="k", campaign_id="NAN", caller=CALLER,
                                     source_commit="x")
        self.assertEqual((len(gen.requests), len(crit.requests)), (0, 0))
        self.assertTrue(all(r["execution_status"] == "not_run" and r["error_code"] == c.BUDGET_EXHAUSTED for r in result["rows"]))
        with self.assertRaises(c.ReviewError):                               # plafond de campagne invalide : refusé avant tout
            runner.run_campaign(corp.load_corpus(), generator=gen, critic=crit, budget=Budget(float("nan")), gen_prices=PRICES,
                                critic_prices=PRICES, gen_model="g", critic_model="k", campaign_id="NAN", caller=CALLER, source_commit="x")

    def test_finite_nonneg_helper(self):
        self.assertTrue(all(finite_nonneg(v) for v in (0, 0.0, 1, 1e-9, 12345.6)))
        self.assertFalse(any(finite_nonneg(v) for v in self.BAD))


class TestBlock3OfflineBoundary(unittest.TestCase):
    """Pas de `NetworkBlocked` ici : ces tests prouvent la garde du RUNNER, pas un patch de test."""

    def setUp(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(8)
        self.server.settimeout(0.4)
        self.addr = self.server.getsockname()
        self.addCleanup(self.server.close)

    def connections_received(self) -> int:
        count = 0
        while True:
            try:
                conn, _ = self.server.accept()
            except (socket.timeout, TimeoutError):
                return count
            conn.close()
            count += 1

    def campaign(self, generator, critic=None):
        return runner.run_campaign(corp.load_corpus(), generator=generator, critic=critic or simulated_critic(), budget=Budget(5.0),
                                   gen_prices=PRICES, critic_prices=PRICES, gen_model="g", critic_model="k", campaign_id="OFF",
                                   caller=Caller(ORG, ACC), source_commit="x")

    def evil(self, attack):
        """Fournisseur malveillant : tente `attack`, AVALE l'exception, puis renvoie une réponse sans texte."""
        def provider(request):
            try:
                attack()
            except BaseException:  # noqa: BLE001 - un fournisseur hostile cache l'erreur
                pass
            return ProviderResult(text=None, error="hostile", usage={"input": 1, "output": 1})
        return offline(provider)

    def test_control_the_loopback_connection_does_succeed_outside_a_campaign(self):
        client = socket.create_connection(self.addr, timeout=1)
        client.close()
        self.assertEqual(self.connections_received(), 1)      # sans la garde, la connexion aboutit : le test ci-dessous est donc probant

    def test_a_raw_callable_is_refused_before_any_call(self):
        calls = []
        with self.assertRaises(TypeError):
            self.campaign(lambda request: calls.append(request))
        with self.assertRaises(TypeError):
            self.campaign(simulated_generator(), critic=lambda request: calls.append(request))
        self.assertEqual(calls, [])
        with self.assertRaises(TypeError):
            OfflineProvider("not callable")

    def test_every_network_route_is_really_blocked_for_the_generator(self):
        import urllib.request
        routes = {
            "create_connection": lambda: socket.create_connection(self.addr, timeout=1),
            "socket.connect": lambda: socket.socket().connect(self.addr),
            "_socket.connect": lambda: __import__("_socket").socket().connect(self.addr),
            "urllib": lambda: urllib.request.urlopen(f"http://{self.addr[0]}:{self.addr[1]}/", timeout=1),
            "dns": lambda: socket.getaddrinfo("example.invalid", 80),
            "sendto": lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", self.addr),
        }
        try:
            import requests
            routes["requests"] = lambda: requests.get(f"http://{self.addr[0]}:{self.addr[1]}/", timeout=1)
        except ImportError:
            pass
        for name, attack in routes.items():
            result = self.campaign(self.evil(attack))
            self.assertGreaterEqual(result["summary"]["network"]["attempts_blocked"], 1, name)
            self.assertTrue(result["summary"]["halted_on_hidden_retry"], name)          # la campagne s'arrête dès la première tentative
            self.assertEqual(result["summary"]["logical_calls"]["generation"], 1, name)
        self.assertEqual(self.connections_received(), 0)                                  # AUCUNE connexion n'a atteint le serveur

    def test_a_malicious_critic_is_blocked_too(self):
        attack = lambda: socket.create_connection(self.addr, timeout=1)  # noqa: E731
        result = self.campaign(simulated_generator(), critic=self.evil(attack))
        self.assertGreaterEqual(result["summary"]["network"]["attempts_blocked"], 1)
        self.assertEqual(self.connections_received(), 0)

    def test_processes_and_native_loading_are_blocked_inside_a_campaign(self):
        import os
        import subprocess
        attacks = [lambda: subprocess.Popen(["curl", f"http://{self.addr[0]}:{self.addr[1]}/"]),
                   lambda: os.system(f"curl http://{self.addr[0]}:{self.addr[1]}/"),
                   lambda: __import__("ctypes").CDLL(None)]
        for attack in attacks:
            result = self.campaign(self.evil(attack))
            self.assertGreaterEqual(result["summary"]["network"]["attempts_blocked"], 1)
        self.assertEqual(self.connections_received(), 0)

    def test_the_guard_is_scoped_to_the_campaign_and_nested_use_is_safe(self):
        with network_denied():
            with network_denied():
                with self.assertRaises(OfflineViolation):
                    socket.create_connection(self.addr, timeout=1)
            with self.assertRaises(OfflineViolation):   # la sortie du niveau interne ne lève pas la garde externe
                socket.create_connection(self.addr, timeout=1)
        socket.create_connection(self.addr, timeout=1).close()   # hors garde : de nouveau possible
        self.assertEqual(self.connections_received(), 1)

    def test_an_honest_offline_campaign_is_unaffected_and_reports_zero_blocked_attempts(self):
        result = self.campaign(simulated_generator())
        self.assertEqual((result["summary"]["network"]["attempts_blocked"], result["summary"]["logical_calls_total"]), (0, 40))
        self.assertFalse(result["summary"]["halted_on_hidden_retry"])


if __name__ == "__main__":
    unittest.main()
