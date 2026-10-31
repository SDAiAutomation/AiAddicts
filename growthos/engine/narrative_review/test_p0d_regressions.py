"""Régressions des défauts du contre-audit Codex (PR #104 à c5e3b91) : plafond d'appels atomique (P0-1), corps protégé (P0-3), politique fail-closed (P1-2), Budget.reconcile.

L'arrêt sur coût inconnu (P0-2) est couvert dans test_harness.py (générateur à texte None/usage None, délais dépassés, réponse partielle, critique indisponible)."""
from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.p0d import authorization as au
from growthos.engine.narrative_review.p0d import profiles as pf
from growthos.engine.narrative_review.p0d import tokenizer as tk
from growthos.engine.narrative_review.p0d import transport as tr
from growthos.engine.narrative_review.providers import Budget, Prices, ProviderResult
from growthos.engine.narrative_review.test_p0d_gates import (MODEL, PROFILE, RECORD, FakeSender, completion, good_auth, open_window, request)

REQ = {"role": "generation", "system": "S" * 100, "user": "U" * 100, "max_output_tokens": 50, "timeout_s": 30}


def setUpModule():
    pf.register_profile(PROFILE)
    unittest.addModuleCleanup(pf._profiles.pop, MODEL, None)


def dates():
    now = datetime.now(timezone.utc)
    return {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(),
            "prices_as_of": (now - timedelta(days=2)).date().isoformat()}


def transport(sender, **over):
    return tr.MeteredTransport(sender, open_window(**{**dates(), **over}), body_validator=lambda r, a: None)


class SlowSender:
    """Fournisseur lent : chaque envoi dure `delay` s, ce qui élargit la fenêtre de course du défaut d'origine."""

    def __init__(self, delay=0.05, boom=None):
        self.calls, self.delay, self.boom, self._lock = [], delay, boom, threading.Lock()

    def __call__(self, req):
        with self._lock:
            self.calls.append(req)
        time.sleep(self.delay)
        if self.boom:
            raise self.boom
        return tr.HttpResponse(200, {}, completion())


def hammer(t, n):
    """n threads lancent un envoi en même temps ; retourne (réussites, refus ReviewError, échecs transport)."""
    barrier, out, lock = threading.Barrier(n), {"ok": 0, "refused": 0, "failed": 0}, threading.Lock()

    def work():
        barrier.wait()
        try:
            t.send(request())
            key = "ok"
        except c.ReviewError:
            key = "refused"
        except tr.TransportError:
            key = "failed"
        with lock:
            out[key] += 1
    threads = [threading.Thread(target=work) for _ in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(30)
    return out


class TestAtomicCallCap(unittest.TestCase):
    def test_two_concurrent_calls_with_a_cap_of_one_send_exactly_once(self):      # reproduction de Codex : 2 envois avec max_logical_calls=1
        for _ in range(5):
            sender = SlowSender()
            out = hammer(transport(sender, max_logical_calls=1), 2)
            self.assertEqual(len(sender.calls), 1)
            self.assertEqual((out["ok"], out["refused"]), (1, 1))

    def test_many_threads_never_exceed_the_cap_even_with_a_slow_provider(self):
        for cap in (1, 3, 7):
            sender = SlowSender(delay=0.02)
            t = transport(sender, max_logical_calls=cap)
            t.max_queue_wait_s = 60
            out = hammer(t, 24)
            self.assertEqual(len(sender.calls), cap)
            self.assertEqual((out["ok"], out["refused"]), (cap, 24 - cap))
            self.assertEqual((len(t.attempts), t.slots_used()), (cap, cap))

    def test_an_exception_after_the_send_still_consumes_the_slot(self):
        sender = SlowSender(delay=0, boom=TimeoutError("t"))
        t = transport(sender, max_logical_calls=2)
        out = hammer(t, 6)
        self.assertEqual((len(sender.calls), out["failed"], out["refused"]), (2, 2, 4))      # un envoi qui échoue ne rend JAMAIS son créneau

    def test_a_failure_before_the_send_returns_the_slot(self):
        sender = SlowSender(delay=0)
        t = tr.MeteredTransport(sender, open_window(**dates(), max_logical_calls=1), body_validator=lambda r, a: (_ for _ in ()).throw(c.ReviewError(c.INVALID_RESPONSE, "bad body")))
        for _ in range(3):
            with self.assertRaises(c.ReviewError):
                t.send(request())
        self.assertEqual((sender.calls, t.slots_used()), ([], 0))                               # rien n'est parti : aucun créneau consommé
        t.body_validator = lambda r, a: None
        t.send(request())                                                                       # le seul créneau est intact
        self.assertEqual(len(sender.calls), 1)

    def test_stop_while_queued_refuses_the_waiting_calls_and_returns_their_slots(self):
        sender = SlowSender(delay=0.3)
        t = transport(sender, max_logical_calls=10)
        t.max_queue_wait_s = 30
        first = threading.Thread(target=lambda: t.send(request()))
        first.start()
        time.sleep(0.05)
        waiting = []
        threads = [threading.Thread(target=lambda: waiting.append(self._try(t))) for _ in range(3)]
        for th in threads:
            th.start()
        time.sleep(0.05)
        t.stop("owner stop")
        for th in threads + [first]:
            th.join(30)
        self.assertEqual(len(sender.calls), 1)                                                  # seul l'envoi déjà en vol est parti
        self.assertEqual(waiting.count("refused"), 3)
        self.assertEqual(t.slots_used(), 1)
        with self.assertRaises(c.ReviewError):
            t.send(request())

    @staticmethod
    def _try(t):
        try:
            t.send(request())
            return "ok"
        except c.ReviewError:
            return "refused"
        except tr.TransportError:
            return "failed"

    def test_a_queue_timeout_sends_nothing_and_returns_the_slot(self):
        sender = SlowSender(delay=0.4)
        t = transport(sender, max_logical_calls=5)
        t.max_queue_wait_s = 0.05
        first = threading.Thread(target=lambda: t.send(request()))
        first.start()
        time.sleep(0.05)
        with self.assertRaises(c.ReviewError):
            t.send(request())
        first.join(30)
        self.assertEqual((len(sender.calls), t.slots_used()), (1, 1))

    def test_no_body_validator_means_no_send(self):
        sender = FakeSender()
        with self.assertRaises(c.ReviewError):
            tr.MeteredTransport(sender, open_window(**dates())).send(request())
        self.assertEqual(sender.calls, [])

    def test_the_window_expiring_while_queued_sends_nothing(self):
        sender = SlowSender(delay=0.3)
        now = datetime.now(timezone.utc)
        t = tr.MeteredTransport(sender, open_window(approved_at=(now - timedelta(hours=1)).isoformat(), expires_at=(now + timedelta(seconds=1)).isoformat(),
                                                    prices_as_of=dates()["prices_as_of"]), body_validator=lambda r, a: None)
        first = threading.Thread(target=lambda: t.send(request()))
        first.start()
        time.sleep(1.3)                                                                          # la fenêtre expire pendant que le 1er envoi dure
        with self.assertRaises(c.ReviewError):
            t.send(request())
        first.join(30)
        self.assertEqual(len(sender.calls), 1)


class TestProtectedBody(unittest.TestCase):
    """Reproduction de Codex : `extra_body` écrasait model, max_tokens et ajoutait n/stream. Aucun corps non conforme ne doit atteindre l'émetteur."""

    def provider(self, extra=None, sender=None, profile=None):
        sender = sender or FakeSender()
        t = tr.MeteredTransport(sender, open_window(**dates()))
        return tr.ChatCompletionsProvider(t, api_key=lambda: "k", extra_body=extra), sender

    def test_extra_body_cannot_overwrite_or_add_protected_parameters(self):
        for extra in ({"model": "expensive-model"}, {"max_tokens": 10**9}, {"n": 8}, {"stream": True}, {"messages": []}, {"tools": []}, {"best_of": 4},
                      {"reasoning_effort": "high"}, {"thinking": {"budget_tokens": 10**6}}, {"max_completion_tokens": 10**6}, {"unknown_param": 1}):
            provider, sender = self.provider(extra)
            with self.assertRaises(c.ReviewError, msg=extra):
                provider(REQ)
            self.assertEqual(sender.calls, [], extra)

    def test_the_body_actually_sent_is_exactly_the_campaign_body(self):
        provider, sender = self.provider()
        provider({**REQ, "max_output_tokens": 10**9})
        body = json.loads(sender.calls[0].body)
        self.assertEqual(sorted(body), ["max_tokens", "messages", "model"])
        self.assertEqual((body["model"], body["max_tokens"]), (MODEL, 4000))                  # plafond ramené à l'autorisation

    def test_the_final_body_validator_rejects_every_malformed_body_before_the_send(self):
        auth = au.CampaignAuthorization(good_auth())
        good = {"model": MODEL, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], "max_tokens": 100}
        validate = lambda body: tr.profile_body_validator(request(body=body if isinstance(body, bytes) else json.dumps(body).encode()), auth)  # noqa: E731
        validate(good)
        bad = {
            "other model": {**good, "model": "expensive-model"}, "cap too high": {**good, "max_tokens": 10**9}, "cap zero": {**good, "max_tokens": 0},
            "cap float": {**good, "max_tokens": 10.5}, "cap bool": {**good, "max_tokens": True}, "cap string": {**good, "max_tokens": "100"},
            "n": {**good, "n": 8}, "stream": {**good, "stream": True}, "extra key": {**good, "foo": 1}, "no model": {k: v for k, v in good.items() if k != "model"},
            "no cap": {k: v for k, v in good.items() if k != "max_tokens"}, "one message": {**good, "messages": good["messages"][:1]},
            "three messages": {**good, "messages": good["messages"] + [{"role": "user", "content": "x"}]},
            "wrong role": {**good, "messages": [{"role": "user", "content": "s"}, {"role": "user", "content": "u"}]},
            "content list": {**good, "messages": [{"role": "system", "content": ["s"]}, good["messages"][1]]},
            "message extra key": {**good, "messages": [{"role": "system", "content": "s", "name": "x"}, good["messages"][1]]},
            "messages not a list": {**good, "messages": "oops"}, "second cap name": {**good, "max_completion_tokens": 10**6},
            "reasoning": {**good, "reasoning_effort": "high"}, "body is a list": [good], "body is a string": "x",
            "duplicate key": b'{"model":"model-x","model":"expensive","messages":[],"max_tokens":1}', "NaN": b'{"model":"model-x","messages":[],"max_tokens":NaN}',
            "not json": b"not json", "empty": b""}
        for label, body in bad.items():
            with self.assertRaises(c.ReviewError, msg=label):
                validate(body)

    def test_an_unknown_model_means_no_call(self):
        sender = FakeSender()
        t = tr.MeteredTransport(sender, open_window(**dates()))
        provider = tr.ChatCompletionsProvider(t, api_key=lambda: "k")
        auth_model = t.window.check().raw["model"]
        pf._profiles.pop(auth_model)
        self.addCleanup(pf.register_profile, PROFILE)
        with self.assertRaises(c.ReviewError):                                                  # profil disparu après l'ouverture : la fenêtre se ferme
            provider(REQ)
        self.assertEqual(sender.calls, [])


class TestFailClosed(unittest.TestCase):
    def test_window_refuses_to_open_for_a_model_without_profile_or_with_inconsistent_policy(self):
        with self.assertRaises(c.ReviewError):
            open_window(**dates(), model="model-without-profile")
        with self.assertRaises(c.ReviewError):
            open_window(**dates(), reasoning_policy="included_in_max_output")                  # le profil dit « pas de raisonnement »

    def test_window_refuses_an_unvalidated_or_mismatched_tokenizer_record(self):
        bad_samples = [("S" * 100, "U" * 100, 400)] * 25                                        # le fournisseur compte PLUS que l'estimation : non validé
        failed = tk.validate_counter(tk.CharHeuristic(), MODEL, bad_samples)
        self.assertFalse(failed.ok)
        with self.assertRaises(c.ReviewError):
            open_window(**dates(), _record=failed, tokenizer_validation_sha256=failed.sha256)
        few = tk.validate_counter(tk.CharHeuristic(), MODEL, [("S" * 100, "U" * 100, 90)] * 3)  # trop peu d'échantillons
        self.assertFalse(few.ok)
        with self.assertRaises(c.ReviewError):
            open_window(**dates(), _record=few, tokenizer_validation_sha256=few.sha256)
        with self.assertRaises(c.ReviewError):
            open_window(**dates(), tokenizer_validation_sha256="0" * 64)                        # empreinte autre que celle de l'enregistrement

    def test_incomplete_prices_or_separate_cap_without_its_fields_are_invalid(self):
        for over in ({"input_per_m": None}, {"output_per_m": float("nan")}, {"output_per_m": -1}, {"prices_source": ""}, {"reasoning_policy": "separate_cap"},
                     {"reasoning_cap_tokens": 100}):
            self.assertTrue(au.validate(good_auth(**over), now=datetime(2026, 11, 3, 10, tzinfo=timezone.utc), corpus_sha256=good_auth()["corpus_sha256"],
                                        baseline_rendered_sha256=good_auth()["baseline_rendered_sha256"]), over)

    def test_billed_reasoning_on_a_model_without_reasoning_stops_the_transport(self):
        sender = FakeSender(body=completion("x", prompt=50, completion_tokens=10, reasoning_tokens=0, completion_tokens_details={"reasoning_tokens": 7}))
        t = tr.MeteredTransport(sender, open_window(**dates()))
        provider = tr.ChatCompletionsProvider(t, api_key=lambda: "k")
        result = provider(REQ)
        self.assertIsNone(result.usage)
        self.assertIsNotNone(t.tripped)
        with self.assertRaises(c.ReviewError):
            provider(REQ)
        self.assertEqual(len(sender.calls), 1)

    def test_output_above_the_authorised_cap_is_an_incident(self):
        sender = FakeSender(body=completion("x", prompt=50, completion_tokens=9999))
        t = tr.MeteredTransport(sender, open_window(**dates()))
        result = tr.ChatCompletionsProvider(t, api_key=lambda: "k")(REQ)
        self.assertIsNone(result.usage)
        self.assertIn("above the authorised cap", result.error)
        self.assertIsNotNone(t.tripped)

    def test_a_truncated_finish_reason_is_a_partial_response(self):
        body = json.dumps({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}], "usage": {"prompt_tokens": 50, "completion_tokens": 10}}).encode()
        result = tr.ChatCompletionsProvider(tr.MeteredTransport(FakeSender(body=body), open_window(**dates())), api_key=lambda: "k")(REQ)
        self.assertTrue(result.partial)


class TestBudgetReconcile(unittest.TestCase):
    PRICES = Prices(input_per_m=1.0, output_per_m=4.0)

    def budget(self):
        return Budget(1.0)

    def test_an_unknown_cost_stays_reserved_and_blocks_new_reservations_until_reconciled(self):
        b = self.budget()
        b.reserve("A", 0.1)
        b.settle("A", None)
        self.assertEqual((b.settled_usd, list(b.unreconciled)), (0, ["A"]))
        self.assertGreaterEqual(b.committed(), 0.1)                                             # jamais traité comme un coût nul
        with self.assertRaises(c.ReviewError):
            b.reserve("B", 0.01)
        b.reconcile("A", 0.05, note="invoice 2026-11-03")
        self.assertEqual(list(b.unreconciled), [])
        self.assertAlmostEqual(b.settled_usd, 0.05)
        b.reserve("B", 0.01)

    def test_reconcile_requires_a_known_label_a_finite_amount_and_a_note(self):
        b = self.budget()
        b.reserve("A", 0.1)
        b.settle("A", None)
        for args in (("ZZ", 0.1, "n"), ("A", float("nan"), "n"), ("A", -1.0, "n"), ("A", 0.1, ""), ("A", 0.1, "   ")):
            with self.assertRaises((c.ReviewError, ValueError), msg=args):
                b.reconcile(args[0], args[1], note=args[2])
        self.assertEqual(list(b.unreconciled), ["A"])

    def test_a_reconciled_amount_above_the_reservation_is_counted_as_an_overrun(self):
        b = self.budget()
        b.reserve("A", 0.1)
        b.settle("A", None)
        b.reconcile("A", 0.3, note="invoice")
        self.assertGreaterEqual(b.settled_usd, 0.3)



# --- Contre-audit Codex à 9575e6a : plafond de raisonnement, réservation unique, autorisation immuable, fenêtre réseau --------------------------

RMODEL = "model-r"
RPROFILE = pf.BodyPolicy(model=RMODEL, max_output_param="max_tokens", reasoning_policy="separate_cap", tokenizer_id=tk.HEURISTIC_ID, reasoning_param="budget_tokens")
RRECORD = tk.validate_counter(tk.CharHeuristic(), RMODEL, [("S" * 100, "U" * 100, 90)] * 25)
RAUTH = dict(model=RMODEL, reasoning_policy="separate_cap", reasoning_cap_tokens=100, reasoning_per_m=8.0, tokenizer_validation_sha256=RRECORD.sha256, _record=RRECORD)


def reasoning_window(**over):
    return open_window(**{**dates(), **RAUTH, **over})


class TestReasoningCap(unittest.TestCase):
    """Cas exact de Codex : reasoning_cap_tokens = 100, extra_body = {"budget_tokens": 999999}, profil separate_cap -> rejeté AVANT tout envoi."""

    def setUp(self):
        pf.register_profile(RPROFILE)
        self.addCleanup(pf._profiles.pop, RMODEL, None)

    def provider(self, extra=None, body=None, **over):
        sender = FakeSender(body=body)
        t = tr.MeteredTransport(sender, reasoning_window(**over))
        return tr.ChatCompletionsProvider(t, api_key=lambda: "k", extra_body=extra), sender, t

    def test_a_caller_cannot_raise_the_reasoning_cap_through_extra_body(self):
        for extra in ({"budget_tokens": 999999}, {"budget_tokens": 100}, {"budget_tokens": 1}, {"reasoning_effort": "high"}, {"thinking": {"budget_tokens": 999999}},
                      {"max_reasoning_tokens": 10**6}, {"thinking_budget": 10**6}):
            provider, sender, _ = self.provider(extra)
            with self.assertRaises(c.ReviewError, msg=extra):
                provider(REQ)
            self.assertEqual(sender.calls, [], extra)                                            # rien n'est parti

    def test_the_reasoning_parameter_actually_sent_is_exactly_the_approved_cap(self):
        provider, sender, _ = self.provider(body=completion("x", prompt=50, completion_tokens=10, completion_tokens_details={"reasoning_tokens": 40}))
        result = provider(REQ)
        sent = json.loads(sender.calls[0].body)
        self.assertEqual((sent["budget_tokens"], sent["model"], sent["max_tokens"]), (100, RMODEL, 50))
        self.assertEqual(sorted(sent), ["budget_tokens", "max_tokens", "messages", "model"])
        self.assertEqual(result.usage, {"input": 50, "output": 10, "reasoning": 40})
        provider, sender, _ = self.provider(extra=None, reasoning_cap_tokens=250)
        provider(REQ)
        self.assertEqual(json.loads(sender.calls[0].body)["budget_tokens"], 250)                 # construit depuis l'autorisation, pas depuis une constante

    def test_a_forged_body_is_refused_by_the_transport_validator_before_the_sender(self):
        sender = FakeSender()
        t = tr.MeteredTransport(sender, reasoning_window())
        t.body_validator = tr.profile_body_validator
        base = {"model": RMODEL, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}], "max_tokens": 50}
        for value in (999999, 101, 99, 0, -1, True, "100", 100.0, None, [100]):
            with self.assertRaises(c.ReviewError, msg=value):
                t.send(request(body=json.dumps({**base, "budget_tokens": value}).encode()))
        with self.assertRaises(c.ReviewError):
            t.send(request(body=json.dumps(base).encode()))                                      # paramètre absent
        self.assertEqual(sender.calls, [])
        t.send(request(body=json.dumps({**base, "budget_tokens": 100}).encode()))                # le seul corps conforme part
        self.assertEqual(len(sender.calls), 1)

    def test_a_profile_cannot_declare_the_reasoning_parameter_as_a_caller_extra(self):
        for extra in ({"budget_tokens": lambda v: True}, {"reasoning_effort": lambda v: True}):
            with self.assertRaises(c.ReviewError):
                pf.register_profile(pf.BodyPolicy(model="model-bad", max_output_param="max_tokens", reasoning_policy="separate_cap", tokenizer_id=tk.HEURISTIC_ID,
                                                  reasoning_param="budget_tokens", allowed_extra=extra))
        with self.assertRaises(c.ReviewError):                                                   # séparé sans paramètre de raisonnement connu
            pf.register_profile(pf.BodyPolicy(model="model-bad", max_output_param="max_tokens", reasoning_policy="separate_cap", tokenizer_id=tk.HEURISTIC_ID))
        with self.assertRaises(c.ReviewError):                                                   # paramètre de raisonnement sur un modèle qui n'en a pas
            pf.register_profile(pf.BodyPolicy(model="model-bad", max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID,
                                              allowed_extra={"reasoning_effort": lambda v: True}))

    def test_reasoning_tokens_above_the_cap_are_an_incident_and_stop_the_transport(self):
        provider, sender, t = self.provider(body=completion("x", prompt=50, completion_tokens=10, completion_tokens_details={"reasoning_tokens": 101}))
        result = provider(REQ)
        self.assertIsNone(result.usage)
        self.assertIsNotNone(t.tripped)
        with self.assertRaises(c.ReviewError):
            provider(REQ)
        self.assertEqual(len(sender.calls), 1)

    def test_missing_reasoning_usage_under_a_separate_unit_means_unknown_cost(self):
        provider, _, _ = self.provider(body=completion("x", prompt=50, completion_tokens=10))
        self.assertIsNone(provider(REQ).usage)                                                   # unité facturable non renvoyée : coût inconnu, jamais zéro


class SpyBudget(Budget):
    def __init__(self, ceiling):
        super().__init__(ceiling)
        self.amounts = []

    def reserve(self, label, max_usd):
        self.amounts.append(max_usd)
        return super().reserve(label, max_usd)


class TestUnifiedReservation(unittest.TestCase):
    def setUp(self):
        from growthos.engine.narrative_review.harness import policy
        cm = policy.baseline_override("synthetic")
        cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)

    def run_campaign(self, gen_prices, critic_prices, budget, generator=None):
        from growthos.engine.narrative_review.harness import runner
        from growthos.engine.narrative_review.harness.simulation import simulated_critic, simulated_generator
        from growthos.engine.narrative_review.reviewer import Caller
        return runner.run_campaign(runner.corp.load_corpus() if hasattr(runner, "corp") else __import__("growthos.engine.narrative_review.harness.corpus", fromlist=["x"]).load_corpus(),
                                   generator=generator or simulated_generator(), critic=simulated_critic(), budget=budget, gen_prices=gen_prices, critic_prices=critic_prices,
                                   gen_model="g", critic_model="k", campaign_id="H", caller=Caller("o", "a"), source_commit="x", strata=("standard",))

    def test_the_four_users_of_the_formula_agree_for_every_billable_unit(self):
        from growthos.engine.narrative_review.providers import max_call_usd
        from growthos.engine.narrative_review.reviewer import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS
        for over, expected in (({}, (16000 * 1.0 + 4000 * 4.0) / 1e6),
                               (RAUTH, (16000 * 1.0 + 4000 * 4.0 + 100 * 8.0) / 1e6)):
            raw = good_auth(**{k: v for k, v in over.items() if k != "_record"})
            auth = au.CampaignAuthorization(raw)
            self.assertAlmostEqual(au.max_call_usd(raw), expected)                                              # autorisation
            self.assertAlmostEqual(max_call_usd(auth.prices, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS), expected)     # harness / critique / futur exécuteur
            self.assertEqual(au.max_call_usd(raw), max_call_usd(auth.prices, raw["max_input_tokens"], raw["max_output_tokens"]))

    def test_the_harness_and_the_critic_reserve_the_full_amount_including_reasoning(self):
        prices = Prices(1.0, 4.0, reasoning_per_m=8.0, reasoning_cap_tokens=100)
        budget = SpyBudget(50.0)
        self.run_campaign(prices, prices, budget)
        full = (16000 * 1.0 + 4000 * 4.0 + 100 * 8.0) / 1e6
        self.assertTrue(budget.amounts)
        self.assertTrue(all(abs(a - full) < 1e-12 for a in budget.amounts), set(budget.amounts))             # génération ET critique : la même réservation complète

    def test_an_unpriced_or_uncapped_unit_means_no_call(self):
        from growthos.engine.narrative_review.providers import max_call_usd
        with self.assertRaises(c.ReviewError):
            Prices(1.0, 4.0, reasoning_per_m=8.0)                                                           # prix sans plafond
        with self.assertRaises(c.ReviewError):
            Prices(1.0, 4.0, reasoning_cap_tokens=100)                                                      # plafond sans prix
        for bad in (0, -5, 1.5, True):
            with self.assertRaises(c.ReviewError):
                Prices(1.0, 4.0, reasoning_per_m=8.0, reasoning_cap_tokens=bad)
        forged = Prices(1.0, 4.0)
        object.__setattr__(forged, "reasoning_per_m", 8.0)                                                  # contournement par mutation : la formule le revalide
        self.assertIsNone(max_call_usd(forged, 16000, 4000))
        for over in ({"reasoning_policy": "separate_cap"}, {"reasoning_policy": "separate_cap", "reasoning_cap_tokens": 100}, {"reasoning_cap_tokens": 100, "reasoning_per_m": 8.0}):
            self.assertTrue(au.validate(good_auth(**over), now=datetime(2026, 11, 3, 10, tzinfo=timezone.utc)), over)

    def test_a_reasoning_priced_campaign_with_usage_lacking_reasoning_stops_on_unknown_cost(self):
        from growthos.engine.narrative_review.harness.offline import offline
        from growthos.engine.narrative_review.harness.simulation import simulated_generator
        prices = Prices(1.0, 4.0, reasoning_per_m=8.0, reasoning_cap_tokens=100)
        inner, n = simulated_generator(), {"n": 0}

        def gen(request_):
            n["n"] += 1
            r = inner(request_)
            return ProviderResult(text=r.text, usage={"input": 10, "output": 10}, latency_s=1.0)
        result = self.run_campaign(prices, prices, Budget(50.0), generator=offline(gen))
        self.assertEqual(n["n"], 1)
        self.assertIn("UNKNOWN_USAGE", result["summary"]["halt_reasons"])

    def test_overrun_above_the_full_reservation_stops_and_a_ceiling_below_one_call_refuses(self):
        from growthos.engine.narrative_review.harness.offline import offline
        from growthos.engine.narrative_review.harness.simulation import simulated_generator
        prices = Prices(1.0, 4.0, reasoning_per_m=8.0, reasoning_cap_tokens=100)
        inner = simulated_generator()
        result = self.run_campaign(prices, prices, Budget(1000.0), generator=offline(
            lambda r: ProviderResult(text=inner(r).text, usage={"input": 10, "output": 10, "reasoning": 10**7}, latency_s=1.0)))
        self.assertIn("COST_EXCEEDED_RESERVATION", result["summary"]["halt_reasons"])
        tiny = SpyBudget(0.001)                                                                             # < 0,0328 $ : pas même un appel complet
        result = self.run_campaign(prices, prices, tiny)
        self.assertEqual(result["summary"]["calls"]["generation"] if "calls" in result["summary"] else 0, 0)

    def test_concurrent_reservations_never_exceed_the_ceiling(self):
        for ceiling, each, fits in ((1.0, 0.3, 3), (0.05, 0.05, 1), (1.0, 2.0, 0)):
            b = Budget(ceiling)
            barrier, ok, lock = threading.Barrier(16), [0], threading.Lock()

            def work(i):
                barrier.wait()
                try:
                    b.reserve(f"L{i}", each)
                    with lock:
                        ok[0] += 1
                except c.ReviewError:
                    pass
            threads = [threading.Thread(target=work, args=(i,)) for i in range(16)]
            for th in threads:
                th.start()
            for th in threads:
                th.join(30)
            self.assertEqual(ok[0], fits)
            self.assertLessEqual(b.committed(), ceiling + 1e-9)

    def test_the_authorization_limits_must_equal_the_harness_limits(self):
        for over in ({"max_input_tokens": 100_000}, {"max_output_tokens": 10}, {"max_input_tokens": 15_999}):
            self.assertTrue(au.validate(good_auth(**over), now=datetime(2026, 11, 3, 10, tzinfo=timezone.utc)), over)


class TestImmutableAuthorization(unittest.TestCase):
    def tearDown(self):
        pf.register_profile(PROFILE)

    def sender_and_provider(self, **over):
        sender = FakeSender()
        t = tr.MeteredTransport(sender, open_window(**{**dates(), **over}))
        return sender, t, tr.ChatCompletionsProvider(t, api_key=lambda: "k")

    def test_approved_parameters_are_frozen_copies(self):
        raw = good_auth()
        auth = au.CampaignAuthorization(raw)
        digest = auth.digest
        raw["ceiling_usd"] = 10**9
        raw["topics"].append("N99")
        self.assertEqual((auth.raw["ceiling_usd"], auth.digest), (5.0, digest))
        with self.assertRaises(TypeError):
            auth.raw["ceiling_usd"] = 10**9
        with self.assertRaises(AttributeError):
            auth.raw["topics"].append("N99")
        with self.assertRaises(Exception):
            auth.raw = {}

    def test_tampering_with_the_authorization_after_opening_is_refused_before_the_send(self):
        sender, t, provider = self.sender_and_provider()
        provider(REQ)
        forged = au.CampaignAuthorization({**au._thaw(t.window._auth.raw), "ceiling_usd": 10**6, "max_logical_calls": 20})
        t.window._auth = forged
        with self.assertRaises(c.ReviewError):
            provider(REQ)
        with self.assertRaises(c.ReviewError):
            t.send(request())
        self.assertEqual(len(sender.calls), 1)                                                   # la fenêtre est fermée définitivement
        with self.assertRaises(c.ReviewError):
            t.window.check()

    def test_in_place_mutation_of_the_frozen_raw_through_private_attributes_is_detected(self):
        sender, t, provider = self.sender_and_provider()
        object.__setattr__(t.window._auth, "raw", au._freeze({**au._thaw(t.window._auth.raw), "input_per_m": 0.0}))   # tarifs réduits en douce
        with self.assertRaises(c.ReviewError):
            provider(REQ)
        self.assertEqual(sender.calls, [])

    def test_replacing_or_altering_the_model_profile_after_opening_is_refused(self):
        for replacement in (pf.BodyPolicy(model=MODEL, max_output_param="max_completion_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID),
                            pf.BodyPolicy(model=MODEL, max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID,
                                          allowed_extra={"temperature": lambda v: True}),
                            pf.BodyPolicy(model=MODEL, max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID)):   # même contenu, autre objet
            sender, t, provider = self.sender_and_provider()
            pf._profiles[MODEL] = replacement
            with self.assertRaises(c.ReviewError):
                provider(REQ)
            self.assertEqual(sender.calls, [])
            pf.register_profile(PROFILE)

    def test_a_profile_cannot_be_mutated_in_place(self):
        with self.assertRaises(Exception):
            PROFILE.allowed_extra["n"] = lambda v: True
        with self.assertRaises(Exception):
            PROFILE.model = "other"

    def test_the_network_state_is_rechecked_before_every_send_and_any_doubt_closes_the_window(self):
        state = {"ok": True, "calls": 0}

        def egress_check():
            state["calls"] += 1
            if not state["ok"]:
                raise RuntimeError("broker no longer in the attested state")
        w = au.Window()
        w.open(au.CampaignAuthorization(good_auth(**dates())), egress_attestation_sha256="e" * 64, tokenizer_validation=RECORD, corpus_sha256=good_auth()["corpus_sha256"],
               egress_check=egress_check)
        sender = FakeSender()
        t = tr.MeteredTransport(sender, w, body_validator=lambda r, a: None)
        t.send(request())
        self.assertGreaterEqual(state["calls"], 2)                                               # avant la réservation ET avant l'envoi
        state["ok"] = False
        with self.assertRaises(c.ReviewError):
            t.send(request())
        state["ok"] = True
        with self.assertRaises(c.ReviewError):                                                   # fermée pour de bon : le retour à la normale ne rouvre rien
            t.send(request())
        self.assertEqual(len(sender.calls), 1)

    def test_a_tampered_attestation_or_tokenizer_record_closes_the_window(self):
        for field, value in (("egress_attestation_sha256", "d" * 64), ("tokenizer_validation_sha256", "d" * 64)):
            sender, t, provider = self.sender_and_provider()
            object.__setattr__(t.window._auth, "raw", au._freeze({**au._thaw(t.window._auth.raw), field: value}))
            with self.assertRaises(c.ReviewError):
                t.send(request())
            self.assertEqual(sender.calls, [])

    def test_an_expired_authorization_cannot_be_opened_and_a_window_cannot_be_reopened(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(c.ReviewError):
            open_window(approved_at=(now - timedelta(hours=3)).isoformat(), expires_at=(now - timedelta(hours=1)).isoformat(), prices_as_of=dates()["prices_as_of"])
        w = open_window(**dates())
        with self.assertRaises(c.ReviewError):
            w.open(au.CampaignAuthorization(good_auth(**dates())), egress_attestation_sha256="e" * 64, tokenizer_validation=RECORD)


class TestNetworkWindow(unittest.TestCase):
    def setUp(self):
        from growthos.engine.narrative_review.test_p0d_egress import NOW, PLAN, attest, simulated
        self.eg, self.NOW, self.PLAN, self.attest, self.simulated = __import__("growthos.engine.narrative_review.p0d.egress", fromlist=["x"]), NOW, PLAN, attest, simulated

    def test_the_plan_must_match_the_authorization_at_the_effective_opening_instant(self):
        eg, raw = self.eg, good_auth()
        self.assertEqual(eg.check_consistency(self.PLAN, raw, now=self.NOW), [])
        self.assertTrue(eg.check_consistency(self.PLAN, {**raw, "expires_at": "2026-11-03T20:00:00+00:00"}, now=self.NOW))     # fins différentes
        self.assertTrue(eg.check_consistency(self.PLAN, raw, now=self.NOW + timedelta(hours=12)))                              # déjà expirée
        self.assertTrue(eg.check_consistency(self.PLAN, raw, now=datetime(2026, 11, 1, tzinfo=timezone.utc)))                  # plus de 48 h devant
        self.assertTrue(eg.check_consistency(self.PLAN, {**raw, "provider_host": "other.example.com"}, now=self.NOW))
        self.assertTrue(eg.check_consistency(self.PLAN, {**raw, "expires_at": "tomorrow"}, now=self.NOW))
        self.assertTrue(eg.check_consistency(self.PLAN, {**raw, "expires_at": "2026-11-03T21:00:00"}, now=self.NOW))            # sans fuseau
        same_instant = {**raw, "expires_at": "2026-11-03T22:00:00+01:00"}
        self.assertEqual(eg.check_consistency(self.PLAN, same_instant, now=self.NOW), [])                                      # même instant, autre fuseau

    def test_no_open_script_is_produced_for_an_expired_window_and_the_script_rechecks_the_clock(self):
        eg = self.eg
        for now in (self.NOW + timedelta(hours=11), self.NOW + timedelta(days=30)):
            with self.assertRaises(c.ReviewError):
                eg.open_script(self.PLAN, now=now)
        script = eg.open_script(self.PLAN, now=self.NOW)
        self.assertIn("UtcNow", script)
        self.assertLess(script.index("UtcNow"), script.index("Remove-NetFirewallRule"))
        self.assertIn("Profile", script)

    def test_a_rule_limited_to_some_windows_profiles_is_not_a_block(self):
        eg = self.eg
        state = self.simulated("rest")
        for rule in state:
            if "HARNESS" in rule["Name"]:
                rule["Profile"] = "Domain, Private"                                                  # ne bloque pas le profil Public
        parsed = eg.parse_firewall_state(json.dumps(state))
        self.assertTrue(eg.reach(self.PLAN.harness_program, parsed, port=None, protocol="Any"))      # le harness atteindrait le réseau
        self.assertFalse(self.attest(state).ok)
        for rule in self.simulated("rest"):
            pass
        state = self.simulated("rest")
        next(r for r in state if "OUTSIDE" in r["Name"])["Profile"] = "Public"
        result = self.attest(state)
        self.assertFalse(result.ok)
        self.assertTrue(eg.reach(self.PLAN.broker_program, eg.parse_firewall_state(json.dumps(state))))

    def test_a_state_without_profile_information_is_an_error_not_a_pass(self):
        eg = self.eg
        state = self.simulated("rest")
        for rule in state:
            del rule["Profile"]
        with self.assertRaises(ValueError):
            eg.parse_firewall_state(json.dumps(state))

    def test_any_uncertainty_keeps_the_gate(self):
        eg = self.eg
        steps = eg.open_steps(self.PLAN)
        self.assertEqual([(op, r["name"].rsplit("-", 1)[-1]) for op, r in steps], [("remove", "GATE")])          # l'ouverture ne retire que le verrou
        self.assertFalse(self.attest([], ).ok)
        self.assertFalse(self.attest(self.simulated("open"), expect="rest").ok)

if __name__ == "__main__":
    unittest.main()
