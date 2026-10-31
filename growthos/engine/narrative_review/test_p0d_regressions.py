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
from growthos.engine.narrative_review.providers import Budget, Prices
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
        with self.assertRaises(pf.ModelUnknown):
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


if __name__ == "__main__":
    unittest.main()
