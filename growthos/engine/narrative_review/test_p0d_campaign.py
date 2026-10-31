"""Une seule tentative en vol par campagne, journal financier durable, reprise après crash, dépendances du tokenizer. Émetteurs FACTICES ; aucun réseau."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.p0d import profiles as pf
from growthos.engine.narrative_review.p0d import tokenizer as tk
from growthos.engine.narrative_review.p0d.ledger import CampaignLedger, LedgerError
from growthos.engine.narrative_review.test_p0d_executor import GOOD_BODY, REQ, Rig
from growthos.engine.narrative_review.test_p0d_gates import MODEL, PROFILE, FakeSender

ROOT = Path(__file__).resolve().parents[3]
NO_USAGE = json.dumps({"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}).encode()


def setUpModule():
    pf.register_profile(PROFILE)
    unittest.addModuleCleanup(pf._profiles.pop, MODEL, None)


class HardCrash(BaseException):
    """Mort du processus : plus aucune écriture, aucun nettoyage."""


class CrashLedger(CampaignLedger):
    dead = False
    crash_at = None

    def _connect(self):
        if self.dead:
            raise HardCrash("the process is dead")
        return super()._connect()

    def _fault(self, point):
        if point == self.crash_at:
            self.dead = True
            raise HardCrash(point)


def crash_hook(point_name):
    box = {}

    def hook(point):
        if point == point_name:
            box["rig"].ledger.dead = True
            raise HardCrash(point)
    return box, hook


def restart(old, **kw):
    """Le processus est mort : l'OS relâche le verrou de fichier ; un nouveau processus rouvre le même journal avec une fenêtre, un transport et un budget neufs."""
    old.ledger.close()
    return Rig(resume=old, **kw)


class TestSingleAttemptInFlight(unittest.TestCase):
    def gate_account(self, rig):
        paused, resume = threading.Event(), threading.Event()
        original = rig.executor._account

        def gated(*args, **kwargs):
            paused.set()
            if not resume.wait(30):
                raise AssertionError("never resumed")
            return original(*args, **kwargs)
        rig.executor._account = gated
        return paused, resume

    def test_codex_scenario_two_threads_first_response_without_usage_pause_before_accounting(self):
        rig = Rig(sender=FakeSender(body=NO_USAGE))
        paused, resume = self.gate_account(rig)
        results = {}
        t1 = threading.Thread(target=lambda: results.__setitem__(1, rig.executor.execute(REQ)))
        t2 = threading.Thread(target=lambda: results.__setitem__(2, rig.executor.execute(REQ)))
        t1.start()
        self.assertTrue(paused.wait(30))                                          # la 1re réponse est reçue, la comptabilisation n'a pas eu lieu
        t2.start()
        time.sleep(0.5)
        self.assertEqual(len(rig.sender.calls), 1)                                # la 2e tentative n'a PAS pu émettre
        self.assertTrue(t2.is_alive())                                            # elle attend la résolution de la 1re
        self.assertEqual(rig.ledger.unresolved(), [rig.ledger.attempts()[0]["label"]])
        resume.set()
        t1.join(30), t2.join(30)
        self.assertEqual((results[1].status, results[2].status), ("failed_after_send", "halted"))
        self.assertEqual(len(rig.sender.calls), 1)                                # EXACTEMENT un envoi
        self.assertEqual(len(rig.ledger.attempts()), 1)                           # la 2e n'a même pas réservé
        self.assertIsNotNone(rig.ledger.halted())

    def test_several_executors_on_the_same_campaign_cannot_bypass_the_guarantee(self):
        a = Rig(sender=FakeSender(body=NO_USAGE))
        b = Rig(resume=a, sender=FakeSender(body=GOOD_BODY))                    # autre exécuteur, autre transport, autre fenêtre, autre budget : même campagne
        paused, resume = self.gate_account(a)
        results = {}
        t1 = threading.Thread(target=lambda: results.__setitem__("a", a.executor.execute(REQ)))
        t2 = threading.Thread(target=lambda: results.__setitem__("b", b.executor.execute(REQ)))
        t1.start()
        self.assertTrue(paused.wait(30))
        t2.start()
        time.sleep(0.5)
        self.assertEqual((len(a.sender.calls), len(b.sender.calls)), (1, 0))
        resume.set()
        t1.join(30), t2.join(30)
        self.assertEqual((results["a"].status, results["b"].status), ("failed_after_send", "halted"))
        self.assertEqual(len(a.sender.calls) + len(b.sender.calls), 1)
        self.assertEqual(b.executor.execute(REQ).status, "halted")

    def test_many_threads_over_two_executors_send_exactly_cap_times_never_overlapping(self):
        in_flight, peak, lock = [0], [0], threading.Lock()

        class Probe(FakeSender):
            def __call__(inner, req):
                with lock:
                    in_flight[0] += 1
                    peak[0] = max(peak[0], in_flight[0])
                time.sleep(0.01)
                try:
                    return super().__call__(req)
                finally:
                    with lock:
                        in_flight[0] -= 1
        a = Rig(sender=Probe(body=GOOD_BODY), max_logical_calls=5)
        b = Rig(resume=a, sender=Probe(body=GOOD_BODY), max_logical_calls=5)
        threads = [threading.Thread(target=(a if i % 2 else b).executor.execute, args=(REQ,)) for i in range(14)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        self.assertEqual(len(a.sender.calls) + len(b.sender.calls), 5)
        self.assertEqual(peak[0], 1)                                               # jamais deux envois simultanés dans la campagne

    def test_timeout_and_unknown_cost_block_the_campaign_and_keep_the_reservation(self):
        rig = Rig(sender=FakeSender(boom=TimeoutError("t")))
        result = rig.executor.execute(REQ)
        self.assertEqual(result.status, "failed_after_send")
        attempt = rig.ledger.attempts()[0]
        self.assertEqual((attempt["state"], attempt["max_usd"] > 0, rig.ledger.halted()), ("unreconciled", True, "PROVIDER_ERROR_OR_INCIDENT"))
        self.assertGreater(rig.ledger.snapshot()["committed_usd"], 0)             # réservation conservée
        self.assertEqual(rig.executor.execute(REQ).status, "halted")
        self.assertEqual(len(rig.sender.calls), 1)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "l.sqlite"
        self.ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=3)
        self.addCleanup(lambda: self.ledger.close())

    def test_every_attempt_has_a_unique_id_a_maximum_a_state_and_timestamps(self):
        self.ledger.begin_attempt("a", 0.1)
        row = self.ledger.attempts()[0]
        self.assertEqual((row["label"], row["max_usd"], row["state"], row["seq"]), ("a", 0.1, "reserved", 1))
        self.assertTrue(row["created_at"].endswith("+00:00") and row["updated_at"])
        self.ledger.mark_sending("a")
        self.ledger.settle("a", 0.05)
        self.assertEqual([r[2] for r in self.ledger.events()], ["campaign_created", "reserved", "sending", "settled"])

    def test_no_double_reservation_and_no_label_reuse(self):
        self.ledger.begin_attempt("a", 0.1)
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("b", 0.1)                                    # une tentative non résolue : pas de seconde réservation
        self.ledger.release("a")
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("a", 0.1)                                    # une étiquette n'est jamais réutilisée
        self.ledger.begin_attempt("b", 0.1)

    def test_the_state_machine_refuses_every_illegal_transition(self):
        self.ledger.begin_attempt("a", 0.1)
        for action in (lambda: self.ledger.settle("a", 0.1), lambda: self.ledger.mark_unreconciled("a", "x"), lambda: self.ledger.reconcile("a", 0.1, "n")):
            with self.assertRaises(LedgerError):
                action()                                                           # `reserved` ne se règle ni ne se réconcilie
        self.ledger.mark_sending("a")
        for action in (lambda: self.ledger.release("a"), lambda: self.ledger.mark_sending("a"), lambda: self.ledger.reconcile("a", 0.1, "n")):
            with self.assertRaises(LedgerError):
                action()                                                           # `sending` ne se libère JAMAIS
        self.ledger.settle("a", 0.04)
        for action in (lambda: self.ledger.settle("a", 0.1), lambda: self.ledger.release("a"), lambda: self.ledger.mark_unreconciled("a", "x")):
            with self.assertRaises(LedgerError):
                action()
        with self.assertRaises(LedgerError):
            self.ledger.settle("unknown", 0.1)

    def test_amounts_are_validated(self):
        for bad in (0, -1, float("nan"), float("inf"), None, True, "1"):
            with self.assertRaises(LedgerError, msg=bad):
                self.ledger.begin_attempt(f"x{bad}", bad)
        self.ledger.begin_attempt("a", 0.1)
        self.ledger.mark_sending("a")
        for bad in (-1, float("nan"), None, True):
            with self.assertRaises(LedgerError, msg=bad):
                self.ledger.settle("a", bad)

    def test_the_ceiling_and_the_call_cap_are_durable(self):
        self.ledger.begin_attempt("a", 0.6)
        self.ledger.release("a")
        self.ledger.begin_attempt("b", 0.6)
        self.ledger.mark_sending("b")
        self.ledger.settle("b", 0.6)
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("c", 0.5)                                    # 0,6 réglé + 0,5 > 1,0
        for name in ("c", "d"):
            self.ledger.begin_attempt(name, 0.1)
            self.ledger.mark_sending(name)
            self.ledger.settle(name, 0.01)
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("e", 0.01)                                   # 3 appels émis = plafond

    def test_reopening_with_another_ceiling_cap_or_campaign_is_refused(self):
        self.ledger.close()
        for kw in ({"ceiling_usd": 2.0, "max_calls": 3, "campaign_id": "C1"}, {"ceiling_usd": 1.0, "max_calls": 9, "campaign_id": "C1"}, {"ceiling_usd": 1.0, "max_calls": 3, "campaign_id": "C2"}):
            with self.assertRaises(LedgerError):
                CampaignLedger(self.path, **kw)
        self.ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=3)

    def test_the_halt_survives_reopening_and_only_explicit_steps_clear_it(self):
        self.ledger.begin_attempt("a", 0.1)
        self.ledger.mark_sending("a")
        self.ledger.mark_unreconciled("a", "UNKNOWN_USAGE")
        self.ledger.close()
        self.ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=3)
        self.assertEqual(self.ledger.halted(), "UNKNOWN_USAGE")
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("b", 0.1)
        with self.assertRaises(LedgerError):
            self.ledger.clear_halt("trying to skip the reconciliation")             # tant qu'une tentative est non résolue
        with self.assertRaises(LedgerError):
            self.ledger.reconcile("a", 0.05, "")                                    # note obligatoire
        self.ledger.reconcile("a", 0.05, "invoice read")
        self.assertEqual(self.ledger.halted(), "UNKNOWN_USAGE")                     # la réconciliation seule ne débloque pas
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("b", 0.1)
        self.ledger.clear_halt("owner reviewed the incident")
        self.ledger.begin_attempt("b", 0.1)


class TestCrashRecovery(unittest.TestCase):
    def crashed_rig(self, point=None, sender=None):
        box, hook = crash_hook(point)
        rig = Rig(ledger_cls=CrashLedger, fault_hook=hook, sender=sender)
        box["rig"] = rig
        return rig

    def test_crash_before_emission_leaves_a_released_reservation_and_an_open_campaign(self):
        rig = self.crashed_rig("before_emit")
        with self.assertRaises(HardCrash):
            rig.executor.execute(REQ)
        self.assertEqual(rig.sender.calls, [])
        after = restart(rig, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual([state for _, state in after.ledger.recovered], ["reserved"])
        self.assertEqual((after.ledger.attempts()[0]["state"], after.ledger.halted()), ("released", None))   # prouvé non envoyé : libérée
        self.assertEqual(after.executor.execute(REQ).status, "completed")
        self.assertEqual(len(after.sender.calls), 1)                                # exactement un envoi au total
        self.assertEqual(sorted({a["seq"] for a in after.ledger.attempts()}), [1, 2])

    def test_crash_right_after_the_marker_is_uncertain_and_blocks_even_though_nothing_was_sent(self):
        rig = self.crashed_rig("after_mark_sending")
        with self.assertRaises(HardCrash):
            rig.executor.execute(REQ)
        self.assertEqual(rig.sender.calls, [])
        after = restart(rig, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual((after.ledger.attempts()[0]["state"], after.ledger.halted()), ("unreconciled", "RECOVERED_UNCERTAIN_ATTEMPT"))
        self.assertEqual(after.executor.execute(REQ).status, "halted")
        self.assertEqual(after.sender.calls, [])
        self.assertEqual(list(after.budget.unreconciled), [after.ledger.attempts()[0]["label"]])    # miroir remis en état

    def test_crash_immediately_after_the_emission_blocks_and_never_resends(self):
        box = {}

        class Dying(FakeSender):
            def __call__(inner, req):
                inner.calls.append(req)
                box["rig"].ledger.dead = True
                raise HardCrash("after emission")
        rig = Rig(ledger_cls=CrashLedger, sender=Dying(body=GOOD_BODY))
        box["rig"] = rig
        with self.assertRaises(HardCrash):
            rig.executor.execute(REQ)
        self.assertEqual(len(rig.sender.calls), 1)
        after = restart(rig, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual((after.ledger.attempts()[0]["state"], after.ledger.halted()), ("unreconciled", "RECOVERED_UNCERTAIN_ATTEMPT"))
        for _ in range(3):
            self.assertEqual(after.executor.execute(REQ).status, "halted")
        self.assertEqual(after.sender.calls, [])                                    # pas de double envoi après redémarrage

    def test_crash_before_accounting_blocks_and_never_resends(self):
        rig = self.crashed_rig("before_accounting")
        with self.assertRaises(HardCrash):
            rig.executor.execute(REQ)
        self.assertEqual(len(rig.sender.calls), 1)
        after = restart(rig, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual(after.ledger.attempts()[0]["state"], "unreconciled")
        self.assertEqual(after.executor.execute(REQ).status, "halted")
        self.assertEqual(after.sender.calls, [])

    def test_crash_during_the_reconciliation_leaves_everything_unresolved_and_a_retry_succeeds(self):
        rig = self.crashed_rig("before_accounting")
        with self.assertRaises(HardCrash):
            rig.executor.execute(REQ)
        second = restart(rig, ledger_cls=CrashLedger)
        label = second.ledger.attempts()[0]["label"]
        second.ledger.crash_at = "before_commit:reconcile"
        with self.assertRaises(HardCrash):
            second.executor.reconcile(label, 0.01, note="invoice")
        third = restart(second)
        self.assertEqual(third.ledger.attempts()[0]["state"], "unreconciled")       # la transaction est tout ou rien : rien n'est écrit
        self.assertIsNone(third.ledger.attempts()[0]["actual_usd"])
        self.assertIsNotNone(third.ledger.halted())
        third.executor.reconcile(label, 0.01, note="invoice")
        self.assertEqual(third.ledger.attempts()[0]["state"], "reconciled")
        self.assertEqual(third.executor.execute(REQ).status, "halted")              # réconcilié mais pas débloqué
        third.ledger.clear_halt("owner reviewed")
        fourth = restart(third, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual(fourth.executor.execute(REQ).status, "completed")
        self.assertAlmostEqual(fourth.ledger.snapshot()["settled_usd"], 0.01 + 0.00049)

    def test_call_cap_and_ceiling_survive_a_restart(self):
        first = Rig(max_logical_calls=2, ceiling_usd=1.0)
        self.assertEqual([first.executor.execute(REQ).status for _ in range(2)], ["completed", "completed"])
        second = restart(first)
        result = second.executor.execute(REQ)                                       # transport neuf : ses créneaux en mémoire sont intacts, le journal refuse
        self.assertEqual((result.status, second.sender.calls), ("refused_before_send", []))
        self.assertEqual(second.ledger.snapshot()["emitted"], 2)
        self.assertEqual(second.budget.reserved, {})

    def test_sequence_numbers_and_labels_never_repeat_across_restarts(self):
        first = Rig()
        first.executor.execute(REQ)
        second = restart(first)
        second.executor.execute(REQ)
        rows = second.ledger.attempts()
        self.assertEqual(([r["seq"] for r in rows], len({r["label"] for r in rows})), ([1, 2], 2))


class TestRealProcessDeath(unittest.TestCase):
    PRELUDE = (f"import sys\nsys.path.insert(0, {str(ROOT)!r})\nfrom growthos.engine.narrative_review.p0d.ledger import CampaignLedger\n"
               "path = sys.argv[1]\n")

    def child(self, code, path):
        return subprocess.run([sys.executable, "-I", "-c", self.PRELUDE + code, str(path)], capture_output=True, text=True, timeout=120)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "l.sqlite"

    def open_here(self):
        ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=3)
        self.addCleanup(ledger.close)
        return ledger

    def test_a_second_process_cannot_own_a_live_campaign(self):
        ledger = self.open_here()
        out = self.child("try:\n    CampaignLedger(path, campaign_id='C1', ceiling_usd=1.0, max_calls=3)\n    print('OPENED')\nexcept Exception as exc:\n    print('REFUSED', type(exc).__name__)\n", self.path)
        self.assertIn("REFUSED", out.stdout, out.stderr)
        ledger.begin_attempt("a", 0.1)                                              # le propriétaire n'est pas perturbé
        self.assertEqual(ledger.unresolved(), ["a"])

    def test_a_process_killed_while_sending_leaves_a_blocked_campaign(self):
        out = self.child("import os\nl = CampaignLedger(path, campaign_id='C1', ceiling_usd=1.0, max_calls=3)\nl.begin_attempt('child', 0.1)\nl.mark_sending('child')\nos._exit(0)\n", self.path)
        self.assertEqual(out.returncode, 0, out.stderr)
        ledger = self.open_here()                                                   # l'OS a relâché le verrou à la mort du processus
        self.assertEqual(ledger.recovered, [("child", "sending")])
        self.assertEqual((ledger.attempts()[0]["state"], ledger.halted()), ("unreconciled", "RECOVERED_UNCERTAIN_ATTEMPT"))
        with self.assertRaises(LedgerError):
            ledger.begin_attempt("again", 0.1)

    def test_a_process_killed_after_reserving_only_leaves_a_released_reservation(self):
        out = self.child("import os\nl = CampaignLedger(path, campaign_id='C1', ceiling_usd=1.0, max_calls=3)\nl.begin_attempt('child', 0.1)\nos._exit(0)\n", self.path)
        self.assertEqual(out.returncode, 0, out.stderr)
        ledger = self.open_here()
        self.assertEqual((ledger.recovered, ledger.attempts()[0]["state"], ledger.halted()), ([("child", "reserved")], "released", None))
        ledger.begin_attempt("again", 0.1)


# --- dépendances indirectes du tokenizer ---------------------------------------------------------------------------------------------------------

def _helper(n):
    return -(-n // 2)


_FACTOR = 1.0


class DepCounter(tk.CharHeuristic):
    id, version = "dep-counter", "1"

    def count(self, text):
        return _helper(int(len(text) * _FACTOR))


class TestTokenizerIndirectDependencies(unittest.TestCase):
    MODEL_DEP = "model-dep"

    def setUp(self):
        tk._registry["dep-counter"] = DepCounter
        self.addCleanup(tk._registry.pop, "dep-counter", None)
        pf.register_profile(pf.BodyPolicy(model=self.MODEL_DEP, max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id="dep-counter"))
        self.addCleanup(pf._profiles.pop, self.MODEL_DEP, None)
        self.module = sys.modules[__name__]
        self.original_helper, self.original_factor = self.module._helper, self.module._FACTOR
        self.addCleanup(self.restore)
        self.record = tk.validate_counter(DepCounter(), self.MODEL_DEP, [("S" * 100, "U" * 100, 90)] * 25)
        self.assertTrue(self.record.ok)

    def restore(self):
        self.module._helper, self.module._FACTOR = self.original_helper, self.original_factor

    def rig(self):
        return Rig(model=self.MODEL_DEP, tokenizer_id="dep-counter", record=self.record, record_sha=self.record.sha256)

    def assert_blocked(self, rig):
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, rig.sender.calls, rig.window.closed), ("refused_before_send", [], True))

    def test_the_baseline_opens_and_sends(self):
        rig = self.rig()
        self.assertEqual(rig.executor.execute(REQ).status, "completed")

    def test_replacing_a_global_function_called_by_count_after_opening_blocks_every_send(self):
        rig = self.rig()
        self.module._helper = lambda n: 0                                           # le scénario de Codex
        self.assert_blocked(rig)

    def test_replacing_it_with_an_identical_looking_function_object_is_also_detected(self):
        rig = self.rig()
        self.module._helper = types.FunctionType(self.original_helper.__code__, vars(self.module).copy())
        self.assert_blocked(rig)

    def test_changing_a_module_constant_used_by_count_is_detected(self):
        rig = self.rig()
        self.module._FACTOR = 0.0
        self.assert_blocked(rig)

    def test_replacing_a_function_of_an_imported_module_used_by_count_is_detected(self):
        class MathCounter(tk.CharHeuristic):
            id, version = "math-counter", "1"

            def count(self, text):
                return math.ceil(len(text) / 2)
        tk._registry["math-counter"] = MathCounter
        self.addCleanup(tk._registry.pop, "math-counter", None)
        pf.register_profile(pf.BodyPolicy(model="model-math", max_output_param="max_tokens", reasoning_policy="not_supported_by_model", tokenizer_id="math-counter"))
        self.addCleanup(pf._profiles.pop, "model-math", None)
        record = tk.validate_counter(MathCounter(), "model-math", [("S" * 100, "U" * 100, 90)] * 25)
        rig = Rig(model="model-math", tokenizer_id="math-counter", record=record, record_sha=record.sha256)
        original = math.ceil
        self.addCleanup(setattr, math, "ceil", original)
        math.ceil = lambda x: 0
        self.assert_blocked(rig)

    def test_a_record_validated_with_other_dependencies_does_not_open_a_window(self):
        self.module._FACTOR = 0.5                                                   # le comportement a changé AVANT l'ouverture
        with self.assertRaises(c.ReviewError) as ctx:
            self.rig()
        self.assertIn("identity", ctx.exception.message)

    def test_the_deterministic_identity_does_not_depend_on_object_addresses(self):
        self.assertEqual(tk.identity(DepCounter()), tk.identity(DepCounter()))
        self.assertNotEqual(tk.identity(DepCounter(), object_ids=True), tk.identity(DepCounter()))
        self.module._FACTOR = 0.5
        self.assertNotEqual(tk.identity(DepCounter()), self.record.impl_sha256)

    def test_a_record_from_another_runtime_is_refused(self):
        forged = tk.ValidationRecord(self.record.tokenizer_id, self.record.model, self.record.samples, self.record.max_reported_over_estimate, self.record.safety, True,
                                     self.record.sha256, self.record.impl_sha256, "0" * 64, self.record.version)
        with self.assertRaises(tk.TokenizerNotValidated):
            tk.require_validated(forged, model=self.MODEL_DEP, tokenizer_id="dep-counter", expected_sha256=self.record.sha256, counter=DepCounter())
        unversioned = tk.ValidationRecord(self.record.tokenizer_id, self.record.model, self.record.samples, self.record.max_reported_over_estimate, self.record.safety, True,
                                          self.record.sha256, self.record.impl_sha256, "", self.record.version)
        with self.assertRaises(tk.TokenizerNotValidated):
            tk.require_validated(unversioned, model=self.MODEL_DEP, tokenizer_id="dep-counter", expected_sha256=self.record.sha256, counter=DepCounter())


if __name__ == "__main__":
    unittest.main()
