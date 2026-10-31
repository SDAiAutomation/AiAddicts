"""Journal canonique unique par campagne, cycle de vie, règlement/arrêt atomiques, profil laboratoire. Émetteurs FACTICES ; aucun réseau ; aucune règle de pare-feu."""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.p0d import authorization as au
from growthos.engine.narrative_review.p0d import egress as eg
from growthos.engine.narrative_review.p0d import executor as ex
from growthos.engine.narrative_review.p0d import profiles as pf
from growthos.engine.narrative_review.p0d.ledger import CampaignLedger, LedgerError, LedgerStore, canonical_root_problems, core_digest, ledger_path
from growthos.engine.narrative_review.test_p0d_campaign import CrashLedger, HardCrash
from growthos.engine.narrative_review.test_p0d_executor import GOOD_BODY, REQ, Rig, dates
from growthos.engine.narrative_review.test_p0d_gates import EGRESS, MODEL, PROFILE, RECORD, FakeSender, controller, good_auth

ROOT_REPO = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


def setUpModule():
    pf.register_profile(PROFILE)
    unittest.addModuleCleanup(pf._profiles.pop, MODEL, None)


def new_root():
    root = os.path.realpath(tempfile.mkdtemp(prefix="p0d-canon-"))
    unittest.addModuleCleanup(shutil.rmtree, root, True)
    return root


def make_link(link: str, target: str):
    """Lien symbolique, sinon jonction Windows (sans droits d'administrateur) ; sinon None."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return link
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True, text=True)
        if done.returncode == 0:
            return link
    return None


class TestOneCanonicalLedgerPerCampaign(unittest.TestCase):
    def test_codex_scenario_same_campaign_one_call_two_executors_two_files_sends_exactly_once(self):
        a = Rig(max_logical_calls=1)
        # un second exécuteur ne peut pas choisir un autre fichier : (1) via le magasin, il n'y a qu'un chemin ; (2) un journal posé ailleurs est refusé par l'exécuteur
        b = Rig(resume=a, sender=FakeSender(body=GOOD_BODY))
        self.assertEqual(a.ledger.path, b.ledger.path)
        other_dir = Path(new_root())
        for unbound in (CampaignLedger(other_dir / "other.sqlite", campaign_id=a.raw["campaign_id"], ceiling_usd=a.raw["ceiling_usd"], max_calls=1),):
            self.addCleanup(unbound.close)
            with self.assertRaises(c.ReviewError) as ctx:
                ex.OfflineExecutor(b.provider, type(b.budget)(5.0), unbound)
            self.assertIn("canonical", ctx.exception.message)
        self.assertEqual(a.executor.execute(REQ).status, "completed")
        self.assertEqual(b.executor.execute(REQ).status, "refused_before_send")         # plafond d'UN appel tenu par le journal unique
        self.assertEqual(len(a.sender.calls) + len(b.sender.calls), 1)                     # exactement un envoi (c'étaient deux sur 530c02a)
        self.assertEqual(len(a.ledger.attempts()), 1)

    def test_a_copy_of_the_ledger_elsewhere_cannot_serve_a_second_executor(self):
        a = Rig(max_logical_calls=1)
        a.executor.execute(REQ)
        copy_path = Path(new_root()) / "copy.sqlite"
        shutil.copy(a.ledger.path, copy_path)                                              # même nonce, mêmes tentatives : une copie parfaite
        forged = CampaignLedger(copy_path, campaign_id=a.raw["campaign_id"], ceiling_usd=a.raw["ceiling_usd"], max_calls=1, _mode="bound",
                                _core=core_digest(a.raw), _binding=a.raw["ledger_binding_sha256"])
        self.addCleanup(forged.close)
        with self.assertRaises(c.ReviewError) as ctx:
            ex.OfflineExecutor(a.provider, type(a.budget)(5.0), forged)                   # identité valide mais mauvais chemin : refusé
        self.assertIn("canonical path", ctx.exception.message)

    def test_an_executor_cannot_use_another_root_or_another_authorization(self):
        a = Rig()
        other_root = new_root()
        with self.assertRaises(LedgerError):
            LedgerStore(other_root).open(a.raw)                                           # l'autorisation nomme une autre racine
        changed = dict(a.raw, ceiling_usd=999.0)
        with self.assertRaises(LedgerError):
            LedgerStore(a.root).open(changed)                                              # cœur de l'autorisation modifié : autre empreinte
        with self.assertRaises(LedgerError):
            LedgerStore(a.root).open(dict(a.raw, ledger_binding_sha256="c" * 64))          # liaison inventée
        with self.assertRaises(LedgerError):
            LedgerStore(a.root).open({k: v for k, v in a.raw.items() if k != "ledger_binding_sha256"})

    def test_an_absent_ledger_is_never_created_and_nothing_is_sent(self):
        a = Rig()
        a.ledger.close()
        shutil.rmtree(a.path.parent)
        with self.assertRaises(LedgerError) as ctx:
            LedgerStore(a.root).open(a.raw)
        self.assertIn("never created", ctx.exception.message)
        self.assertFalse(a.path.parent.exists())                                          # aucune création implicite, pas même un répertoire
        a.path.parent.mkdir(parents=True)                                                  # répertoire recréé mais fichier absent
        with self.assertRaises(LedgerError):
            LedgerStore(a.root).open(a.raw)
        self.assertEqual(list(a.path.parent.iterdir()), [])
        self.assertEqual(a.sender.calls, [])

    def test_a_replaced_or_reset_ledger_is_refused(self):
        a = Rig()
        a.executor.execute(REQ)
        a.ledger.close()
        store = LedgerStore(a.root)
        # 1. remplacé par un journal NEUF de même campagne (sans identité liée)
        a.path.unlink()
        fresh = CampaignLedger(a.path, campaign_id=a.raw["campaign_id"], ceiling_usd=a.raw["ceiling_usd"], max_calls=a.raw["max_logical_calls"])
        fresh.close()
        with self.assertRaises(LedgerError):
            store.open(a.raw)
        # 2. réinitialisé par le magasin : nonce différent
        shutil.rmtree(a.path.parent)
        core = {k: v for k, v in a.raw.items() if k != "ledger_binding_sha256"}
        new_binding = store.initialize(core)
        self.assertNotEqual(new_binding, a.raw["ledger_binding_sha256"])
        with self.assertRaises(LedgerError):
            store.open(a.raw)
        # 3. journal d'une autre racine copié en place
        other = Rig()
        other.ledger.close()
        a.path.unlink()
        shutil.copy(other.path, a.path)
        with self.assertRaises(LedgerError):
            store.open(a.raw)

    def test_a_ledger_replaced_while_the_executor_runs_makes_the_next_attempt_fail_without_send(self):
        a = Rig(max_logical_calls=5)
        self.assertEqual(a.executor.execute(REQ).status, "completed")
        other = Rig()
        other.ledger.close()
        shutil.copy(other.path, a.path)                                                    # le fichier est remplacé sous le processus en cours
        result = a.executor.execute(REQ)
        self.assertEqual(result.status, "halted")
        self.assertIn("ledger unavailable", result.error)
        self.assertEqual(len(a.sender.calls), 1)
        a.path.unlink()                                                                    # puis supprimé
        self.assertEqual(a.executor.execute(REQ).status, "halted")
        self.assertFalse(a.path.exists())                                                  # jamais recréé
        self.assertEqual(len(a.sender.calls), 1)

    def test_initialization_is_explicit_one_shot_and_refuses_any_existing_campaign_directory(self):
        root = new_root()
        store = LedgerStore(root)
        core = good_auth(_binding=False, ledger_root=root, campaign_id="P0D-ONCE")
        binding = store.initialize(core)
        self.assertRegex(binding, r"^[0-9a-f]{64}$")
        with self.assertRaises(LedgerError):
            store.initialize(core)                                                         # pas de réinitialisation
        self.assertEqual(store.path_for("P0D-ONCE"), ledger_path(root, "P0D-ONCE"))
        with self.assertRaises(LedgerError):
            store.initialize(dict(core, ledger_binding_sha256=binding))                    # le cœur ne contient pas la liaison
        with self.assertRaises(LedgerError):
            store.initialize(dict(core, ledger_root=new_root()))                           # autre racine
        ledger = store.open(dict(core, ledger_binding_sha256=binding))
        self.addCleanup(ledger.close)
        self.assertEqual(ledger.binding, binding)

    def test_the_nonce_makes_every_initialization_unique(self):
        root = new_root()
        store = LedgerStore(root)
        core = good_auth(_binding=False, ledger_root=root, campaign_id="P0D-NONCE")
        first = store.initialize(core)
        shutil.rmtree(ledger_path(root, "P0D-NONCE").parent)
        self.assertNotEqual(store.initialize(core), first)

    def test_path_aliases_relative_paths_links_and_hard_links(self):
        root = new_root()
        for bad in (".", "relative/dir", "", None, 7, os.path.join(root, "x", "..", "x"), os.path.join(root, "missing"), root + os.sep + "."):
            self.assertTrue(canonical_root_problems(bad), bad)
        self.assertEqual(canonical_root_problems(root), [])
        link = make_link(os.path.join(new_root(), "alias"), root)
        if link is None:
            self.skipTest("this environment cannot create a symbolic link or junction: alias refusal not exercised here")
        self.assertTrue(canonical_root_problems(link))                                      # l'alias est REFUSÉ, pas résolu
        with self.assertRaises(LedgerError):
            LedgerStore(link)
        self.assertTrue(au.validate(good_auth(ledger_root=link), now=NOW))

    def test_a_ledger_file_that_is_a_link_or_has_several_hard_links_is_refused(self):
        a = Rig()
        a.ledger.close()
        alias = a.path.with_name("alias.sqlite")
        os.link(a.path, alias)                                                              # deux noms pour un même journal
        self.addCleanup(lambda: alias.exists() and alias.unlink())
        with self.assertRaises(LedgerError) as ctx:
            LedgerStore(a.root).open(a.raw)
        self.assertIn("hard links", ctx.exception.message)

    def test_case_aliases_resolve_to_the_same_campaign_lock(self):
        if os.name != "nt":
            self.skipTest("case-insensitive path aliases only exist on Windows")
        a = Rig()
        alias = CampaignLedger(Path(str(a.path).upper()), campaign_id=a.raw["campaign_id"], ceiling_usd=a.raw["ceiling_usd"], max_calls=a.raw["max_logical_calls"])
        self.addCleanup(alias.close)
        self.assertIs(a.ledger._owner, alias._owner)                                       # même clé de verrou : pas de second propriétaire
        self.assertEqual(alias.attempts(), a.ledger.attempts())

    def test_concurrent_executors_over_the_canonical_ledger_send_exactly_the_cap(self):
        a = Rig(max_logical_calls=1)
        b = Rig(resume=a, sender=FakeSender(body=GOOD_BODY))
        threads = [threading.Thread(target=(a if i % 2 else b).executor.execute, args=(REQ,)) for i in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(60)
        self.assertEqual(len(a.sender.calls) + len(b.sender.calls), 1)
        a.ledger.close(), b.ledger.close()
        c_ = LedgerStore(a.root).open(a.raw)                                               # réouverture : la même vérité
        self.addCleanup(c_.close)
        self.assertEqual((c_.snapshot()["emitted"], len(c_.attempts())), (1, 1))

    def test_the_authorization_requires_a_canonical_root_a_binding_and_a_profile(self):
        self.assertEqual(au.validate(good_auth(), now=NOW, corpus_sha256=good_auth()["corpus_sha256"], baseline_rendered_sha256=good_auth()["baseline_rendered_sha256"]), [])
        for bad in ({"ledger_root": "relative"}, {"ledger_root": os.path.join(new_root(), "gone")}, {"ledger_binding_sha256": "short"}, {"network_profile": "staging"}):
            self.assertTrue(au.validate(good_auth(**bad), now=NOW), bad)
        raw = good_auth()
        del raw["ledger_binding_sha256"]
        self.assertTrue(any("ledger_binding_sha256" in p for p in au.validate(raw, now=NOW)))


class TestCanonicalLedgerAcrossProcesses(unittest.TestCase):
    CHILD = ("import json, sys" + chr(10) + f"sys.path.insert(0, {str(ROOT_REPO)!r})" + chr(10) +
             "from growthos.engine.narrative_review.p0d.ledger import LedgerStore" + chr(10) + "raw = json.loads(sys.argv[1])" + chr(10) +
             "try:" + chr(10) + "    LedgerStore(raw['ledger_root']).open(raw).close()" + chr(10) + "    print('OPENED')" + chr(10) +
             "except Exception as exc:" + chr(10) + "    print('REFUSED', type(exc).__name__)" + chr(10))

    def child(self, raw: dict) -> str:
        done = subprocess.run([sys.executable, "-I", "-c", self.CHILD, json.dumps(raw)], capture_output=True, text=True, timeout=120)
        return done.stdout.strip()

    def test_a_second_process_cannot_own_the_canonical_ledger_until_the_first_one_closes(self):
        a = Rig()
        self.assertTrue(self.child(a.raw).startswith("REFUSED"))                            # propriétaire vivant : refus
        self.assertTrue(self.child(dict(a.raw, ceiling_usd=999.0)).startswith("REFUSED"))   # autre autorisation : refus
        a.ledger.close()
        self.assertEqual(self.child(a.raw), "OPENED")                                       # fermé : un autre processus peut reprendre le même journal canonique


class TestLedgerLifecycle(unittest.TestCase):
    PRELUDE = (f"import sys\nsys.path.insert(0, {str(ROOT_REPO)!r})\nfrom growthos.engine.narrative_review.p0d.ledger import CampaignLedger\npath = sys.argv[1]\n")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "l.sqlite"
        self.ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=5)
        self.addCleanup(lambda: self.ledger.close())

    def reopen(self):
        self.ledger.close()
        self.ledger = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=5)
        return self.ledger

    def child_can_open(self):
        code = ("try:\n    CampaignLedger(path, campaign_id='C1', ceiling_usd=1.0, max_calls=5).close()\n    print('OPENED')\nexcept Exception as exc:\n    print('REFUSED')\n")
        out = subprocess.run([sys.executable, "-I", "-c", self.PRELUDE + code, str(self.path)], capture_output=True, text=True, timeout=120)
        self.assertIn(out.stdout.strip(), ("OPENED", "REFUSED"), out.stderr)
        return out.stdout.strip() == "OPENED"

    def test_every_operation_fails_after_close(self):
        self.ledger.begin_attempt("a", 0.1)
        self.ledger.mark_sending("a")
        self.ledger.close()
        self.ledger.close()                                                                  # idempotent
        operations = {"begin": lambda: self.ledger.begin_attempt("b", 0.1), "mark_sending": lambda: self.ledger.mark_sending("a"), "release": lambda: self.ledger.release("a"),
                      "settle": lambda: self.ledger.settle("a", 0.05), "unreconciled": lambda: self.ledger.mark_unreconciled("a", "x"), "halt": lambda: self.ledger.halt("x"),
                      "reconcile": lambda: self.ledger.reconcile("a", 0.05, "n"), "clear_halt": lambda: self.ledger.clear_halt("n"), "halted": lambda: self.ledger.halted(),
                      "unresolved": lambda: self.ledger.unresolved(), "state_of": lambda: self.ledger.state_of("a"), "attempts": lambda: self.ledger.attempts(),
                      "events": lambda: self.ledger.events(), "snapshot": lambda: self.ledger.snapshot(), "critical_section": lambda: self.ledger.critical_section()}
        for name, op in operations.items():
            with self.assertRaises(LedgerError, msg=name):
                op()

    def test_a_closed_instance_creates_no_reservation_and_settles_nothing(self):
        self.ledger.begin_attempt("a", 0.1)
        self.ledger.mark_sending("a")
        self.ledger.close()
        for op in (lambda: self.ledger.begin_attempt("b", 0.1), lambda: self.ledger.settle("a", 0.05), lambda: self.ledger.reconcile("a", 0.05, "n")):
            with self.assertRaises(LedgerError):
                op()
        again = self.reopen()
        self.assertEqual([(r["label"], r["state"]) for r in again.attempts()], [("a", "unreconciled")])   # rien n'a été écrit après la fermeture
        again.reconcile("a", 0.05, "invoice")                                                          # la réconciliation d'une instance ouverte, elle, fonctionne
        self.assertEqual(again.attempts()[0]["state"], "reconciled")

    def test_close_waits_for_an_attempt_in_flight_and_never_releases_the_campaign_lock_early(self):
        inside, leave, closed = threading.Event(), threading.Event(), threading.Event()
        result = {}

        def attempt():
            with self.ledger.critical_section():
                self.ledger.begin_attempt("a", 0.1)
                inside.set()
                leave.wait(30)
                self.ledger.mark_sending("a")                                               # l'instance reste utilisable pendant que close() attend
                result["still_usable"] = self.ledger.state_of("a")
                self.ledger.settle("a", 0.05)

        def closer():
            self.ledger.close(timeout=30)
            closed.set()
        t1, t2 = threading.Thread(target=attempt), threading.Thread(target=closer)
        t1.start()
        self.assertTrue(inside.wait(30))
        t2.start()
        time.sleep(0.5)
        self.assertFalse(closed.is_set())                                                    # close() attend la fin de la tentative
        self.assertFalse(self.child_can_open())                                              # et le verrou de fichier n'a PAS été relâché
        leave.set()
        t1.join(30), t2.join(30)
        self.assertTrue(closed.is_set())
        self.assertEqual(result["still_usable"], "sending")
        with self.assertRaises(LedgerError):
            self.ledger.begin_attempt("late", 0.1)
        self.assertTrue(self.child_can_open())                                               # réouverture par un autre processus : seulement après la fermeture
        again = self.reopen()
        self.assertEqual([(r["label"], r["state"]) for r in again.attempts()], [("a", "settled")])

    def test_closing_from_inside_an_active_attempt_is_refused_and_leaves_the_ledger_usable(self):
        with self.ledger.critical_section():
            self.ledger.begin_attempt("a", 0.1)
            with self.assertRaises(LedgerError):
                self.ledger.close()
            self.assertEqual(self.ledger.unresolved(), ["a"])
        self.ledger.release("a")

    def test_a_close_that_times_out_does_not_close(self):
        inside, leave = threading.Event(), threading.Event()

        def attempt():
            with self.ledger.critical_section():
                inside.set()
                leave.wait(30)
        t = threading.Thread(target=attempt)
        t.start()
        self.assertTrue(inside.wait(30))
        with self.assertRaises(LedgerError):
            self.ledger.close(timeout=0.2)
        leave.set()
        t.join(30)
        self.assertEqual(self.ledger.unresolved(), [])                                      # toujours ouvert et utilisable
        self.ledger.begin_attempt("a", 0.1)

    def test_one_instance_closing_does_not_free_the_lock_while_a_sibling_is_open(self):
        sibling = CampaignLedger(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=5)
        self.addCleanup(sibling.close)
        self.ledger.close()
        self.assertFalse(self.child_can_open())                                              # le frère tient encore la campagne
        sibling.begin_attempt("a", 0.1)
        sibling.release("a")
        sibling.close()
        self.assertTrue(self.child_can_open())

    def test_an_executor_over_a_closed_ledger_reserves_and_sends_nothing(self):
        rig = Rig()
        rig.ledger.close()
        result = rig.executor.execute(REQ)
        self.assertEqual((result.status, rig.sender.calls), ("halted", []))
        self.assertIn("ledger unavailable", result.error)


# --- règlement et arrêt atomiques, pannes aux frontières de transaction ---------------------------------------------------------------------------

class TestAtomicSettlementAndHalt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "l.sqlite"

    def open(self, cls=CampaignLedger):
        ledger = cls(self.path, campaign_id="C1", ceiling_usd=1.0, max_calls=5)
        self.addCleanup(ledger.close)
        return ledger

    def test_codex_scenario_reserved_010_settled_020_crash_before_halted_is_written(self):
        ledger = self.open(CrashLedger)
        ledger.begin_attempt("x", 0.10)
        ledger.mark_sending("x")
        ledger.crash_at = "after_commit:settle"                                              # le règlement est validé sur disque, puis le processus meurt
        with self.assertRaises(HardCrash):
            ledger.settle("x", 0.20)
        ledger.close()
        after = self.open()
        self.assertEqual((after.attempts()[0]["state"], after.attempts()[0]["actual_usd"]), ("settled", 0.2))
        self.assertEqual(after.halted(), "COST_EXCEEDED_RESERVATION")                          # le dépassement bloque TOUJOURS la campagne (c'était None sur 530c02a)
        with self.assertRaises(LedgerError):
            after.begin_attempt("next", 0.1)

    def test_the_overrun_and_the_halt_are_one_transaction(self):
        ledger = self.open()
        ledger.begin_attempt("x", 0.10)
        ledger.mark_sending("x")
        self.assertTrue(ledger.settle("x", 0.20))
        self.assertEqual(ledger.halted(), "COST_EXCEEDED_RESERVATION")
        events = [(kind, detail) for _, label, kind, detail in ledger.events() if kind in ("settled", "halt")]
        self.assertEqual([k for k, _ in events], ["settled", "halt"])

    def test_a_crash_before_the_settlement_commits_leaves_an_uncertain_blocked_campaign(self):
        ledger = self.open(CrashLedger)
        ledger.begin_attempt("x", 0.10)
        ledger.mark_sending("x")
        ledger.crash_at = "before_commit:settle"
        with self.assertRaises(HardCrash):
            ledger.settle("x", 0.20)
        ledger.close()
        after = self.open()
        self.assertEqual((after.attempts()[0]["state"], after.attempts()[0]["actual_usd"], after.halted()), ("unreconciled", None, "RECOVERED_UNCERTAIN_ATTEMPT"))

    def test_a_within_reservation_settlement_with_a_stop_reason_commits_both_together(self):
        for point, expected in (("before_commit:settle", ("unreconciled", "RECOVERED_UNCERTAIN_ATTEMPT")), ("after_commit:settle", ("settled", "PARTIAL_RESPONSE"))):
            self.setUp()
            ledger = self.open(CrashLedger)
            ledger.begin_attempt("x", 0.10)
            ledger.mark_sending("x")
            ledger.crash_at = point
            with self.assertRaises(HardCrash):
                ledger.settle("x", 0.05, halt_reason="PARTIAL_RESPONSE")
            ledger.close()
            after = self.open()
            self.assertEqual((after.attempts()[0]["state"], after.halted()), expected, point)          # jamais « réglé et non bloqué » quand une raison d'arrêt existait

    def test_recovery_blocks_a_legacy_overrun_that_was_settled_without_a_halt(self):
        ledger = self.open()
        ledger.begin_attempt("x", 0.10)
        ledger.mark_sending("x")
        ledger.settle("x", 0.20)
        ledger.clear_halt("simulate a legacy file")                                         # reconstitue un fichier d'avant le correctif : réglé, dépassé, non bloqué
        ledger.close()
        self.assertEqual(self.open().halted(), "COST_EXCEEDED_RESERVATION")                    # la reprise le bloque (filet de sécurité)

    def test_reconciling_above_the_reservation_blocks_in_the_same_transaction(self):
        ledger = self.open()
        ledger.begin_attempt("x", 0.10)
        ledger.mark_sending("x")
        ledger.mark_unreconciled("x", "UNKNOWN_USAGE")
        ledger.reconcile("x", 0.50, "invoice read")
        self.assertEqual(ledger.halted(), "UNKNOWN_USAGE")                                    # le blocage antérieur subsiste ; un dépassement ne le lève jamais

    # --- matrice : chaque transition, chaque frontière de transaction ---------------------------------------------------------------------------

    SCENARIOS = {
        "begin": (lambda L: None, lambda L: L.begin_attempt("x", 0.10)),
        "mark_sending": (lambda L: L.begin_attempt("x", 0.10), lambda L: L.mark_sending("x")),
        "release": (lambda L: L.begin_attempt("x", 0.10), lambda L: L.release("x")),
        "settle": (lambda L: (L.begin_attempt("x", 0.10), L.mark_sending("x")), lambda L: L.settle("x", 0.05)),
        "settle_overrun": (lambda L: (L.begin_attempt("x", 0.10), L.mark_sending("x")), lambda L: L.settle("x", 0.20)),
        "mark_unreconciled": (lambda L: (L.begin_attempt("x", 0.10), L.mark_sending("x")), lambda L: L.mark_unreconciled("x", "UNKNOWN_USAGE")),
        "halt": (lambda L: None, lambda L: L.halt("OPERATOR")),
        "reconcile": (lambda L: (L.begin_attempt("x", 0.10), L.mark_sending("x"), L.mark_unreconciled("x", "UNKNOWN_USAGE")), lambda L: L.reconcile("x", 0.50, "invoice")),
        "clear_halt": (lambda L: (L.begin_attempt("x", 0.10), L.mark_sending("x"), L.settle("x", 0.20)), lambda L: L.clear_halt("owner reviewed")),
    }

    def check_invariants(self, ledger, label):
        rows, halted = ledger.attempts(), ledger.halted()
        self.assertFalse([r for r in rows if r["state"] in ("reserved", "sending")], label)                  # I1 : aucun état transitoire après reprise
        if any(r["state"] == "unreconciled" for r in rows):
            self.assertTrue(halted, label)                                                                      # I2 : une issue incertaine bloque
        for r in rows:                                                                                           # I3 : un dépassement réglé bloque, sauf déblocage explicite postérieur
            if r["state"] in ("settled", "reconciled") and r["actual_usd"] > r["max_usd"] + 1e-12 and not any(e[2] == "halt_cleared" for e in ledger.events()):
                self.assertTrue(halted, label)
        if halted or ledger.unresolved():                                                                        # I4 : nouvelle réservation refusée ssi bloqué ou non résolu
            with self.assertRaises(LedgerError, msg=label):
                ledger.begin_attempt("probe", 0.01)
        else:
            ledger.begin_attempt("probe", 0.01)
            ledger.release("probe")
        self.assertLessEqual(len({r["label"] for r in rows}), len(rows), label)                                 # I5 : étiquettes uniques

    def test_every_transition_survives_a_crash_on_each_side_of_its_commit(self):
        checked = 0
        for name, (prepare, final) in self.SCENARIOS.items():
            op = {"settle_overrun": "settle"}.get(name, name)
            for boundary in ("before_commit", "after_commit"):
                self.setUp()
                ledger = self.open(CrashLedger)
                prepare(ledger)
                ledger.crash_at = f"{boundary}:{op}"
                with self.assertRaises(HardCrash, msg=f"{name}/{boundary}"):
                    final(ledger)
                ledger.close()
                after = self.open()
                self.check_invariants(after, f"{name}/{boundary}")
                checked += 1
        self.assertEqual(checked, 2 * len(self.SCENARIOS))


# --- profil laboratoire ----------------------------------------------------------------------------------------------------------------------------

LAB = dict(campaign_id="LAB-P0D-1", provider_host="provider.lab.invalid", profile="lab", lab_cidr="10.77.0.0/24", provider_ips=("10.77.0.20",))
PLAN_KW = dict(harness_program=r"C:\Python311\python.exe", broker_program=r"C:\p0d\broker\python.exe", window_end_iso="2026-11-03T21:00:00+00:00")


def lab_plan(**over):
    return eg.EgressPlan(**{**PLAN_KW, **LAB, **over})


def prod_plan(**over):
    return eg.EgressPlan(**{**PLAN_KW, "campaign_id": "P0D-TEST", "provider_host": "api.provider-example.com", "provider_ips": ("8.8.4.4",), **over})


def lab_auth(**over):
    return good_auth(**{"network_profile": "lab", "campaign_id": "LAB-P0D-1", "provider_host": "provider.lab.invalid", **over})


class TestLabProfile(unittest.TestCase):
    def test_a_lab_plan_accepts_only_private_lab_addresses_and_a_reserved_host(self):
        self.assertEqual(lab_plan().validate(), [])
        bad = [dict(provider_ips=("8.8.4.4",)), dict(provider_ips=("10.78.0.20",)), dict(provider_ips=("10.77.0.0",)), dict(provider_ips=("10.77.0.255",)), dict(provider_ips=("127.0.0.1",)),
               dict(lab_cidr=""), dict(lab_cidr="8.8.8.0/24"), dict(lab_cidr="10.0.0.0/16", provider_ips=("10.0.0.20",)), dict(lab_cidr="127.0.0.0/24", provider_ips=("127.0.0.20",)),
               dict(lab_cidr="169.254.1.0/24", provider_ips=("169.254.1.20",)), dict(provider_host="api.provider-example.com"), dict(profile="staging")]
        for over in bad:
            self.assertTrue(lab_plan(**over).validate(), over)

    def test_a_production_plan_refuses_private_addresses_lab_markers_and_a_lab_network(self):
        self.assertEqual(prod_plan().validate(), [])
        for over in (dict(provider_ips=("10.77.0.20",)), dict(provider_ips=("192.168.1.5",)), dict(lab_cidr="10.77.0.0/24"), dict(provider_host="provider.lab.invalid")):
            self.assertTrue(prod_plan(**over).validate(), over)

    def test_the_profile_is_part_of_the_plan_and_of_the_attestation(self):
        lab, prod = lab_plan(), prod_plan()
        self.assertNotEqual(eg.plan_sha256(lab), eg.plan_sha256(prod))
        state = [{"Name": r["name"], "DisplayName": r["name"], "Enabled": "True", "Direction": "Outbound", "Action": r["action"], "Profile": "Any", "Program": r["program"],
                  "RemoteAddress": r["remote"], "Protocol": r["protocol"], "RemotePort": r["port"]} for r in eg.rules_for_state(lab, "rest")]
        attestation = eg.attest(lab, eg.parse_firewall_state(json.dumps(state)), expect="rest")
        self.assertEqual((attestation.ok, attestation.network_profile, attestation.plan_sha256), (True, "lab", eg.plan_sha256(lab)))

    def test_the_lab_rules_keep_the_same_default_blocked_property(self):
        plan = lab_plan()
        rest = eg.rules_for_state(plan, "rest")
        self.assertEqual(eg.reach(plan.broker_program, rest), [])
        self.assertEqual(eg.reach(plan.harness_program, rest, port=None, protocol="Any"), [])
        state = []
        for step in eg.install_steps(plan) + eg.open_steps(plan) + eg.close_steps(plan):
            state = eg.apply_step(state, step)
            self.assertTrue(eg.reach_within_provider(plan, state), step[1]["name"])               # chaque étape : jamais plus que l'IP du faux fournisseur
        opened = eg.rules_for_state(plan, "open")
        self.assertEqual([(s, v) for s, e, v in eg.reach(plan.broker_program, opened) if s == e], [(int(ipaddress.ip_address("10.77.0.20")), 4)])
        self.assertEqual(eg.reach(plan.broker_program, opened, port=8443), [])

    def test_a_lab_authorization_and_a_production_authorization_cannot_borrow_each_others_markers(self):
        base = dict(now=NOW)
        self.assertEqual(au.validate(lab_auth(), corpus_sha256=good_auth()["corpus_sha256"], baseline_rendered_sha256=good_auth()["baseline_rendered_sha256"], **base), [])
        for bad in (dict(campaign_id="P0D-TEST"), dict(provider_host="api.provider-example.com")):
            self.assertTrue(au.validate(lab_auth(**bad), **base), bad)                                   # un « lab » sans marqueurs de laboratoire
        for bad in (dict(campaign_id="LAB-X"), dict(provider_host="provider.lab.invalid")):
            self.assertTrue(au.validate(good_auth(**bad), **base), bad)                                  # une production avec des marqueurs de laboratoire

    def test_the_plan_profile_must_match_the_authorization_profile(self):
        self.assertEqual(eg.check_consistency(lab_plan(), lab_auth(expires_at="2026-11-03T21:00:00+00:00"), now=NOW), [])
        self.assertTrue(eg.check_consistency(lab_plan(), good_auth(), now=NOW))                              # plan lab, autorisation de production
        self.assertTrue(eg.check_consistency(prod_plan(), lab_auth(), now=NOW))                              # plan de production, autorisation lab

    def lab_window(self, ctl=None, *, allow_lab=True, **auth_over):
        now = datetime.now(timezone.utc)
        over = {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(), "prices_as_of": (now - timedelta(days=2)).date().isoformat(), **auth_over}
        window = au.Window()
        window.open(au.CampaignAuthorization(lab_auth(**over)), egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD,
                    egress_controller=ctl or controller(network_profile="lab"), allow_lab=allow_lab)
        return window

    def test_a_lab_window_opens_only_explicitly_and_only_with_a_lab_attestation(self):
        window = self.lab_window()
        window.check()
        with self.assertRaises(c.ReviewError):
            self.lab_window(allow_lab=False)                                                          # laboratoire seulement par choix explicite
        with self.assertRaises(c.ReviewError):
            self.lab_window(controller())                                                             # attestation de production pour une autorisation lab
        now = datetime.now(timezone.utc)
        prod_over = {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(), "prices_as_of": (now - timedelta(days=2)).date().isoformat()}
        with self.assertRaises(c.ReviewError):
            au.Window().open(au.CampaignAuthorization(good_auth(**prod_over)), egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD,
                             egress_controller=controller(network_profile="lab"), allow_lab=True)    # attestation lab pour une autorisation de production : refusé même avec allow_lab

    def test_switching_the_attested_profile_during_the_window_closes_it(self):
        ctl = controller(network_profile="lab")
        window = self.lab_window(ctl)
        window.check()
        ctl.network_profile = "production"
        with self.assertRaises(c.ReviewError):
            window.check()
        self.assertTrue(window.closed)

    def test_allow_lab_never_lets_a_production_authorization_use_a_lab_plan(self):
        now = datetime.now(timezone.utc)
        prod_over = {"approved_at": (now - timedelta(hours=1)).isoformat(), "expires_at": (now + timedelta(hours=6)).isoformat(), "prices_as_of": (now - timedelta(days=2)).date().isoformat()}
        for allow in (False, True):
            with self.assertRaises(c.ReviewError):
                au.Window().open(au.CampaignAuthorization(good_auth(**prod_over)), egress_attestation_sha256=EGRESS, tokenizer_validation=RECORD,
                                 egress_controller=controller(network_profile="lab"), allow_lab=allow)


if __name__ == "__main__":
    unittest.main()
