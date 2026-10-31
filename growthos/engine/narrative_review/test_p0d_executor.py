"""Exécuteur P0-D hors ligne : séquence contrôlée, verrouillage du tokenizer, contrôle réseau vivant obligatoire, réservations, arrêts. Émetteurs FACTICES exclusivement ; aucun réseau."""
from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.p0d import authorization as au
from growthos.engine.narrative_review.p0d import egress as eg
from growthos.engine.narrative_review.p0d import executor as ex
from growthos.engine.narrative_review.p0d import profiles as pf
from growthos.engine.narrative_review.p0d import tokenizer as tk
from growthos.engine.narrative_review.p0d import transport as tr
from growthos.engine.narrative_review.providers import Budget, max_call_usd
from growthos.engine.narrative_review.test_p0d_egress import PLAN as EPLAN
from growthos.engine.narrative_review.test_p0d_egress import attest as egress_attest
from growthos.engine.narrative_review.test_p0d_egress import simulated as egress_state
from growthos.engine.narrative_review.test_p0d_gates import (EGRESS, MODEL, PROFILE, RECORD, FakeSender, completion, controller, good_auth)

REQ = {"role": "generation", "system": "S" * 100, "user": "U" * 100, "max_output_tokens": 50, "timeout_s": 30}
GOOD_BODY = json.dumps({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 90, "completion_tokens": 100}}).encode()
EXPECTED_COST = (90 * 1.0 + 100 * 4.0) / 1e6
FULL_STEPS = ("authorization", "fingerprints", "network", "tokenizer", "budget", "reservation", "final_check", "transport", "accounting")


def setUpModule():
    pf.register_profile(PROFILE)
    unittest.addModuleCleanup(pf._profiles.pop, MODEL, None)


class Clock:
    def __init__(self):
        self.now = datetime.now(timezone.utc)

    def __call__(self):
        return self.now


def dates(clock=None):
    now = clock() if clock else datetime.now(timezone.utc)
    return {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(),
            "prices_as_of": (now - timedelta(days=2)).date().isoformat()}


class Boom(BaseException):
    """Interruption qui n'est pas une `Exception` (comme KeyboardInterrupt), sans interrompre le lanceur de tests."""


class Rig:
    """Fenêtre + transport + exécuteur, avec un point d'accroche exécuté APRÈS la validation du corps (donc après tous les contrôles, juste avant le contrôle final)."""

    def __init__(self, *, sender=None, ctl=None, clock=None, hook=None, ceiling=5.0, api_key=lambda: "k", record=None, record_sha=None, **auth_over):
        self.clock, self.ctl = clock or Clock(), ctl or controller()
        self.sender = sender or FakeSender(body=GOOD_BODY)
        self.hook = hook
        self.window = au.Window(clock=self.clock)
        over = {**dates(self.clock), **auth_over}
        if record_sha:
            over["tokenizer_validation_sha256"] = record_sha
        self.window.open(au.CampaignAuthorization(good_auth(**over)), egress_attestation_sha256=over.get("egress_attestation_sha256", EGRESS),
                         tokenizer_validation=record or RECORD, egress_controller=self.ctl)

        def validator(req, auth):
            tr.profile_body_validator(req, auth)
            if self.hook:
                self.hook()
        self.transport = tr.MeteredTransport(self.sender, self.window, body_validator=validator)
        self.provider = tr.ChatCompletionsProvider(self.transport, api_key=api_key)
        self.budget = Budget(ceiling)
        self.executor = ex.OfflineExecutor(self.provider, self.budget)

    def full_cost(self):
        return max_call_usd(self.window._auth.prices, 16000, 4000)


class OtherCounter(tk.CharHeuristic):
    def count(self, text):
        return 0


class TestSequence(unittest.TestCase):
    def test_the_happy_path_runs_every_step_in_order_and_accounts_the_call(self):
        rig = Rig()
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, result.emitted, result.steps), ("completed", True, FULL_STEPS))
        self.assertAlmostEqual(result.estimated_usd, EXPECTED_COST)
        self.assertEqual(len(rig.sender.calls), 1)
        self.assertEqual((rig.budget.reserved, rig.budget.unreconciled), ({}, {}))
        self.assertAlmostEqual(rig.budget.settled_usd, EXPECTED_COST)
        report = rig.executor.report()
        self.assertEqual((report["retries"], report["halted"], report["completed"]), (0, None, 1))

    def test_the_reservation_is_the_full_maximum_of_one_call(self):
        seen = []
        rig = Rig()
        rig.hook = lambda: seen.append(dict(rig.budget.reserved))
        rig.executor.execute(REQ)
        self.assertEqual(len(seen[0]), 1)
        self.assertAlmostEqual(list(seen[0].values())[0], (16000 * 1.0 + 4000 * 4.0) / 1e6)

    def test_expiry_between_reservation_and_send_sends_nothing_and_releases_the_reservation(self):
        clock = Clock()
        rig = Rig(clock=clock)
        rig.hook = lambda: setattr(clock, "now", clock.now + timedelta(hours=7))             # le temps passe après la validation du corps
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, result.emitted), ("refused_before_send", False))
        self.assertEqual(rig.sender.calls, [])
        self.assertEqual((rig.budget.reserved, rig.budget.committed()), ({}, 0))               # libérée : il est PROUVÉ que rien n'est parti
        self.assertEqual(rig.executor.halted(), "WINDOW_CLOSED")
        self.assertEqual(rig.executor.execute(REQ).status, "halted")

    def test_expiry_during_the_send_lets_the_in_flight_call_finish_and_refuses_the_next(self):
        clock = Clock()

        class Sender(FakeSender):
            def __call__(inner, req):
                clock.now += timedelta(hours=7)
                return super().__call__(req)
        rig = Rig(clock=clock, sender=Sender(body=GOOD_BODY))
        self.assertEqual(rig.executor.execute(REQ).status, "completed")
        self.assertEqual(rig.executor.execute(REQ).status, "refused_before_send")
        self.assertEqual(len(rig.sender.calls), 1)

    def test_profile_mutation_after_reservation_is_refused_before_the_send(self):
        for replacement in (pf.BodyPolicy(model=MODEL, max_output_param="max_completion_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID),
                            pf.BodyPolicy(model=MODEL, max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id=tk.HEURISTIC_ID)):
            rig = Rig()
            rig.hook = lambda r=replacement: pf._profiles.__setitem__(MODEL, r)
            self.addCleanup(pf.register_profile, PROFILE)
            result = rig.executor.execute(REQ)
            pf.register_profile(PROFILE)
            self.assertEqual((result.status, rig.sender.calls, rig.budget.committed()), ("refused_before_send", [], 0))

    def test_price_tampering_after_reservation_is_refused_before_the_send(self):
        rig = Rig()

        def tamper():
            raw = au._thaw(rig.window._auth.raw)
            raw["input_per_m"], raw["output_per_m"] = 0.0, 0.0
            object.__setattr__(rig.window._auth, "raw", au._freeze(raw))
        rig.hook = tamper
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, rig.sender.calls, rig.budget.committed()), ("refused_before_send", [], 0))

    def test_an_exception_before_the_send_releases_the_reservation_and_does_not_stop_the_executor(self):
        for label, make in {"api key": lambda: Rig(api_key=lambda: (_ for _ in ()).throw(RuntimeError("no key"))),
                            "missing request field": lambda: Rig(), "body validator": lambda: Rig()}.items():
            rig = make()
            request = {k: v for k, v in REQ.items() if k != "user"} if label == "missing request field" else REQ
            if label == "body validator":
                rig.hook = lambda: (_ for _ in ()).throw(c.ReviewError(c.INVALID_RESPONSE, "refused"))
            result = rig.executor.execute(request)
            self.assertEqual((result.status, result.emitted, rig.sender.calls, rig.budget.committed()), ("refused_before_send", False, [], 0), label)
            self.assertIsNone(rig.executor.halted(), label)
            rig.hook = None
            self.assertEqual(rig.executor.execute(REQ).status, "completed" if label != "api key" else "refused_before_send", label)

    def test_a_non_exception_interruption_before_the_send_releases_and_after_the_send_does_not(self):
        rig = Rig()
        rig.hook = lambda: (_ for _ in ()).throw(Boom())
        with self.assertRaises(Boom):
            rig.executor.execute(REQ)
        self.assertEqual((rig.sender.calls, rig.budget.committed()), ([], 0))

        class Sender(FakeSender):
            def __call__(inner, req):
                inner.calls.append(req)
                raise Boom()
        rig = Rig(sender=Sender(body=GOOD_BODY))
        with self.assertRaises(Boom):
            rig.executor.execute(REQ)
        self.assertEqual((len(rig.sender.calls), len(rig.budget.unreconciled), rig.executor.halted()), (1, 1, "UNKNOWN_COST_AFTER_SEND"))

    def test_a_timeout_after_the_attempt_keeps_the_amount_stops_everything_and_never_retries(self):
        rig = Rig(sender=FakeSender(boom=TimeoutError("t")))
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, result.emitted), ("failed_after_send", True))
        label = result.label
        self.assertEqual(list(rig.budget.unreconciled), [label])
        self.assertGreater(rig.budget.committed(), 0)                                           # jamais traité comme un coût nul
        for _ in range(3):
            self.assertEqual(rig.executor.execute(REQ).status, "halted")
        self.assertEqual(len(rig.sender.calls), 1)                                              # aucun retry
        rig.executor.reconcile(label, 0.01, note="invoice read by the owner")
        self.assertEqual((rig.budget.unreconciled, round(rig.budget.settled_usd, 6)), ({}, 0.01))
        self.assertEqual(rig.executor.execute(REQ).status, "halted")                            # la réconciliation n'enlève pas l'arrêt
        self.assertEqual(len(rig.sender.calls), 1)

    def test_http_errors_redirects_partial_and_unknown_usage_stop_the_executor(self):
        partial = json.dumps({"choices": [{"message": {"content": "x"}, "finish_reason": "length"}], "usage": {"prompt_tokens": 90, "completion_tokens": 100}}).encode()
        no_usage = json.dumps({"choices": [{"message": {"content": "x"}}]}).encode()
        for label, sender, reason, unreconciled in (("429", FakeSender(status=429), "PROVIDER_ERROR_OR_INCIDENT", 1), ("503", FakeSender(status=503), "PROVIDER_ERROR_OR_INCIDENT", 1),
                                                    ("302", FakeSender(status=302), "PROVIDER_ERROR_OR_INCIDENT", 1), ("partial", FakeSender(body=partial), "PARTIAL_RESPONSE", 0),
                                                    ("no usage", FakeSender(body=no_usage), "UNKNOWN_USAGE", 1)):
            rig = Rig(sender=sender)
            result = rig.executor.execute(REQ)
            self.assertEqual(result.status, "failed_after_send", label)
            self.assertEqual(rig.executor.halted(), reason, label)
            self.assertEqual(len(rig.budget.unreconciled), unreconciled, label)
            rig.executor.execute(REQ)
            self.assertEqual(len(sender.calls), 1, label)

    def test_a_tokenizer_underestimate_reported_by_the_provider_is_an_incident(self):
        rig = Rig(sender=FakeSender(body=completion("x", prompt=5000, completion_tokens=10)))
        result = rig.executor.execute(REQ)
        self.assertEqual(result.status, "failed_after_send")
        self.assertIsNone(result.usage)
        self.assertEqual(len(rig.budget.unreconciled), 1)
        self.assertIsNotNone(rig.executor.halted())

    def test_a_call_whose_maximum_exceeds_the_ceiling_is_refused_without_a_send(self):
        rig = Rig(ceiling=0.001)                                                                 # < 0,032 $ : pas même un appel complet
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, rig.sender.calls, rig.budget.committed()), ("refused_before_send", [], 0))
        self.assertIsNone(rig.executor.halted())


class TestConcurrency(unittest.TestCase):
    @staticmethod
    def run_threads(rig, n):
        barrier, results = threading.Barrier(n), []

        def work():
            barrier.wait()
            results.append(rig.executor.execute(REQ))
        threads = [threading.Thread(target=work) for _ in range(n)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        return results

    def test_the_call_cap_and_the_budget_hold_under_concurrent_executions(self):
        class Slow(FakeSender):
            def __call__(inner, req):
                time.sleep(0.02)
                return super().__call__(req)
        rig = Rig(sender=Slow(body=GOOD_BODY), max_logical_calls=3)
        rig.transport.max_queue_wait_s = 60
        results = self.run_threads(rig, 12)
        self.assertEqual(sorted(r.status for r in results).count("completed"), 3)
        self.assertEqual(len(rig.sender.calls), 3)
        self.assertEqual(rig.budget.reserved, {})                                                # les 9 réservations refusées ont toutes été libérées
        self.assertAlmostEqual(rig.budget.committed(), 3 * EXPECTED_COST)
        self.assertEqual(rig.executor.report()["emitted"], 3)

    def test_a_failure_stops_the_queued_executions_before_they_send(self):
        class Failing(FakeSender):
            def __call__(inner, req):
                inner.calls.append(req)
                time.sleep(0.05)
                raise TimeoutError("t")
        sender = Failing()
        rig = Rig(sender=sender)
        rig.transport.max_queue_wait_s = 60
        results = self.run_threads(rig, 10)
        self.assertEqual(len(sender.calls), 1)                                                   # un seul envoi, jamais de second après l'échec
        self.assertEqual(sorted(r.status for r in results).count("failed_after_send"), 1)
        self.assertEqual(len(rig.budget.unreconciled), 1)
        self.assertEqual(rig.budget.reserved, {})

    def test_a_global_stop_refuses_the_waiting_executions_and_releases_their_reservations(self):
        started = threading.Event()

        class Slow(FakeSender):
            def __call__(inner, req):
                started.set()
                time.sleep(0.3)
                return super().__call__(req)
        rig = Rig(sender=Slow(body=GOOD_BODY))
        rig.transport.max_queue_wait_s = 60
        results, threads = [], [threading.Thread(target=lambda: results.append(rig.executor.execute(REQ))) for _ in range(6)]
        for th in threads:
            th.start()
        self.assertTrue(started.wait(10))
        time.sleep(0.1)
        rig.executor.stop("owner stop")
        for th in threads:
            th.join(60)
        self.assertEqual(len(rig.sender.calls), 1)                                               # seul l'envoi déjà en vol est parti
        self.assertEqual(sum(r.status == "refused_before_send" for r in results), 5)
        self.assertEqual(rig.budget.reserved, {})
        self.assertEqual(rig.executor.execute(REQ).status, "halted")


class TestTokenizerPinning(unittest.TestCase):
    def setUp(self):
        self.original = tk._registry[tk.HEURISTIC_ID]
        self.original_count = tk.CharHeuristic.count
        self.addCleanup(self.restore)

    def restore(self):
        tk._registry[tk.HEURISTIC_ID] = self.original
        tk.CharHeuristic.count = self.original_count

    def assert_nothing_sent(self, rig, result):
        self.assertEqual((result.status, rig.sender.calls, rig.budget.committed()), ("refused_before_send", [], 0))
        self.assertTrue(rig.window.closed)

    def test_replacing_the_factory_under_the_same_id_blocks_every_later_send(self):
        rig = Rig()
        tk._registry[tk.HEURISTIC_ID] = OtherCounter                                            # le scénario de Codex
        self.assert_nothing_sent(rig, rig.executor.execute(REQ))
        with self.assertRaises(c.ReviewError):
            rig.provider(REQ)                                                                   # ni par le fournisseur seul
        self.assertEqual(rig.sender.calls, [])

    def test_even_a_behaviourally_identical_replacement_is_refused(self):
        rig = Rig()
        tk._registry[tk.HEURISTIC_ID] = lambda: tk.CharHeuristic()
        self.assert_nothing_sent(rig, rig.executor.execute(REQ))

    def test_substitution_after_the_checks_but_before_the_send_is_caught_by_the_final_check(self):
        rig = Rig()
        rig.hook = lambda: tk._registry.__setitem__(tk.HEURISTIC_ID, OtherCounter)             # entre la validation du corps et l'émission
        self.assert_nothing_sent(rig, rig.executor.execute(REQ))

    def test_patching_the_pinned_implementation_in_place_is_detected(self):
        rig = Rig()
        tk.CharHeuristic.count = lambda self, text: 0
        self.assert_nothing_sent(rig, rig.executor.execute(REQ))

    def test_altering_the_state_of_the_pinned_instance_is_detected(self):
        rig = Rig()
        rig.window.pinned_counter().bias = -1000
        self.assert_nothing_sent(rig, rig.executor.execute(REQ))

    def test_the_pinned_counter_is_used_not_a_fresh_resolution(self):
        rig = Rig()
        self.assertIs(rig.window.pinned_counter(), rig.window.pinned_counter())
        self.assertEqual(rig.executor.execute(REQ).status, "completed")

    def test_a_validation_record_only_covers_the_implementation_that_was_validated(self):
        class Honest(tk.CharHeuristic):
            id = "same-id"

            def count(self, text):
                return -(-len(text) // 2)

        class Lax(tk.CharHeuristic):
            id = "same-id"

            def count(self, text):
                return 0
        tk._registry["same-id"] = Honest
        self.addCleanup(tk._registry.pop, "same-id", None)
        pf.register_profile(pf.BodyPolicy(model="model-same", max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id="same-id"))
        self.addCleanup(pf._profiles.pop, "model-same", None)
        record = tk.validate_counter(Honest(), "model-same", [("S" * 100, "U" * 100, 90)] * 25)
        self.assertTrue(record.ok)
        Rig(model="model-same", tokenizer_id="same-id", record=record, record_sha=record.sha256)       # l'implémentation validée s'ouvre
        tk._registry["same-id"] = Lax                                                                  # une autre implémentation, même identifiant
        with self.assertRaises(c.ReviewError) as ctx:
            Rig(model="model-same", tokenizer_id="same-id", record=record, record_sha=record.sha256)
        self.assertIn("identity", ctx.exception.message)

    def test_concurrent_replacement_while_executions_run_stops_all_sends_afterwards(self):
        class Slow(FakeSender):
            def __call__(inner, req):
                time.sleep(0.01)
                return super().__call__(req)
        rig = Rig(sender=Slow(body=GOOD_BODY), max_logical_calls=20)
        rig.transport.max_queue_wait_s = 60
        stop, results = threading.Event(), []

        def worker():
            while not stop.is_set():
                results.append(rig.executor.execute(REQ))
                if rig.executor.halted():
                    return

        def mutator():
            time.sleep(0.05)
            tk._registry[tk.HEURISTIC_ID] = OtherCounter
        threads = [threading.Thread(target=worker) for _ in range(6)] + [threading.Thread(target=mutator)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        stop.set()
        before = len(rig.sender.calls)
        self.assertTrue(rig.window.closed)
        for _ in range(3):
            self.assertIn(rig.executor.execute(REQ).status, ("halted", "refused_before_send"))
        self.assertEqual(len(rig.sender.calls), before)                                         # plus aucun envoi après la substitution
        self.assertEqual(rig.budget.reserved, {})                                               # aucune réservation orpheline
        self.assertLessEqual(before, 20)


class TestLiveNetworkControl(unittest.TestCase):
    def test_no_controller_no_window(self):
        auth = au.CampaignAuthorization(good_auth(**dates()))
        with self.assertRaises(TypeError):
            au.Window().open(auth, egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD)               # paramètre obligatoire
        for bad in (None, object(), "controller"):
            with self.assertRaises(c.ReviewError):
                au.Window().open(auth, egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD, egress_controller=bad)

    def test_an_error_an_inconsistent_attestation_or_an_unknown_state_refuses_the_opening(self):
        auth = au.CampaignAuthorization(good_auth(**dates()))
        wrong_class = type("Wrong", (eg.EgressController,), {"check": lambda self, expect: "ok"})()
        bad_state = type("BadState", (eg.EgressController,), {"check": lambda self, expect: eg.Attestation(True, (), EGRESS, "open", "p" * 64)})()
        for label, ctl in {"error": controller(fail=RuntimeError("powershell failed")), "not ok": controller(ok=False), "other attestation": eg.FakeEgressController(rest_sha256="d" * 64),
                           "wrong type": wrong_class, "wrong state": bad_state}.items():
            with self.assertRaises(c.ReviewError, msg=label):
                au.Window().open(auth, egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD, egress_controller=ctl)

    def test_every_send_is_preceded_by_a_live_check_and_loss_of_the_attestation_blocks_the_send(self):
        rig = Rig()
        self.assertEqual(rig.executor.execute(REQ).status, "completed")
        self.assertGreaterEqual(rig.ctl.calls.count("open"), 4)                                  # sequence + fournisseur + transport (x2) pour un seul appel
        rig.ctl.ok = False                                                                       # attestation perdue
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, len(rig.sender.calls)), ("refused_before_send", 1))
        rig.ctl.ok = True
        self.assertEqual(rig.executor.execute(REQ).status, "halted")                             # la fenêtre est fermée pour de bon

    def test_loss_between_the_reservation_and_the_send_releases_without_sending(self):
        rig = Rig()
        rig.hook = lambda: setattr(rig.ctl, "fail", RuntimeError("lost"))
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, rig.sender.calls, rig.budget.committed()), ("refused_before_send", [], 0))

    def test_an_attestation_bound_to_another_plan_closes_the_window(self):
        rig = Rig()
        rig.ctl.wrong_plan = True
        self.assertEqual(rig.executor.execute(REQ).status, "refused_before_send")
        self.assertEqual(rig.sender.calls, [])

    def test_the_report_never_presents_a_simulated_controller_as_an_os_proof(self):
        rig = Rig()
        rig.executor.execute(REQ)
        report = rig.executor.report()
        self.assertEqual((report["egress_kind"], report["os_cutoff_proven"]), ("simulated", False))
        self.assertTrue(report["network_proof"].startswith("SIMULATED"))
        self.assertIn("NOT a proof", report["network_proof"])

    def test_a_read_only_os_controller_over_simulated_firewall_output_follows_the_real_state_machine(self):
        state = {"name": "rest"}
        rest_sha = egress_attest(egress_state("rest"), expect="rest").sha256
        ctl = eg.OsReadOnlyEgressController(EPLAN, lambda script: json.dumps(egress_state(state["name"])))
        rig = Rig(ctl=ctl, egress_attestation_sha256=rest_sha)                                   # ouverture : état de repos attesté
        self.assertEqual(rig.window.egress_kind, "os_readonly")
        self.assertEqual(rig.executor.execute(REQ).status, "refused_before_send")                # fenêtre ouverte côté Python mais verrou encore là : état « open » non atteint
        rig = Rig(ctl=ctl, egress_attestation_sha256=rest_sha)
        state["name"] = "open"                                                                   # le propriétaire retire le verrou
        self.assertEqual(rig.executor.execute(REQ).status, "completed")
        state["name"] = "rest"                                                                   # fermeture / expiration / redémarrage : le verrou revient
        self.assertEqual(rig.executor.execute(REQ).status, "refused_before_send")
        self.assertEqual(len(rig.sender.calls), 1)
        self.assertFalse(rig.executor.report()["os_cutoff_proven"])                              # même ici : jamais une preuve de coupure

    def test_an_extra_allow_rule_in_the_live_state_refuses_the_send(self):
        state = egress_state("open")
        rest_sha = egress_attest(egress_state("rest"), expect="rest").sha256
        current = {"state": egress_state("rest")}
        ctl = eg.OsReadOnlyEgressController(EPLAN, lambda script: json.dumps(current["state"]))
        rig = Rig(ctl=ctl, egress_attestation_sha256=rest_sha)
        hole = {**state[0], "Name": "Some-Allow", "Action": "Allow", "Program": EPLAN.broker_program}
        current["state"] = egress_state("open") + [hole]
        self.assertEqual(rig.executor.execute(REQ).status, "refused_before_send")
        self.assertEqual(rig.sender.calls, [])


class TestBudgetRelease(unittest.TestCase):
    def test_only_a_pending_reservation_can_be_released(self):
        b = Budget(1.0)
        with self.assertRaises(c.ReviewError):
            b.release("unknown")
        b.reserve("A", 0.1)
        self.assertEqual(b.release("A"), 0.1)
        with self.assertRaises(c.ReviewError):
            b.release("A")                                                                       # déjà libérée
        b.reserve("B", 0.1)
        b.settle("B", 0.05)
        with self.assertRaises(c.ReviewError):
            b.release("B")                                                                       # réglée : jamais libérable
        b.reserve("C", 0.1)
        b.settle("C", None)
        with self.assertRaises(c.ReviewError):
            b.release("C")                                                                       # non réconciliée : jamais libérable
        self.assertEqual(list(b.unreconciled), ["C"])


if __name__ == "__main__":
    unittest.main()
