"""Mission 3 : préparation HORS LIGNE du pilote Standard (5 sujets, A/B). Répétition à blanc uniquement : aucun pilote, aucun réseau, aucun coût."""
from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import pilot, policy, runner
from growthos.engine.narrative_review.harness.corpus import HoldoutAccessError
from growthos.engine.narrative_review.providers import Prices
from growthos.engine.narrative_review.test_review import NetworkBlocked


def rehearsal(tmp: str, **kw):
    return pilot.rehearse(Path(tmp), **kw)


class TestPilotScope(NetworkBlocked):
    def test_ten_standard_cases_for_the_five_authorised_subjects_only(self):
        cases = runner.plan_cases("X", corp.PILOT_IDS, pilot.PILOT_STRATA)
        self.assertEqual(len(cases), 10)
        self.assertEqual(sorted({k["topic_id"] for k in cases}), sorted(corp.PILOT_IDS))
        self.assertEqual({k["stratum"] for k in cases}, {"standard"})
        self.assertEqual({k["condition"] for k in cases}, {"A", "B"})
        for bad in ((), ("nope",), ("standard", "nope")):
            with self.assertRaises(ValueError):
                runner.plan_cases("X", corp.PILOT_IDS, bad)

    def test_no_development_or_holdout_subject_can_enter(self):
        corpus = corp.load_corpus()
        for tid, topic in corpus["topics"].items():
            if topic["split"] != "pilot":
                with self.assertRaises(HoldoutAccessError, msg=tid):
                    corp.generator_view(corpus, tid, allowed_splits=("pilot",))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(HoldoutAccessError):
            from growthos.engine.narrative_review.harness.simulation import simulated_critic, simulated_generator
            from growthos.engine.narrative_review.providers import Budget
            from growthos.engine.narrative_review.reviewer import Caller
            runner.run_campaign(corpus, generator=simulated_generator(), critic=simulated_critic(), budget=Budget(5.0), gen_prices=pilot.ILLUSTRATIVE_PRICES,
                                critic_prices=pilot.ILLUSTRATIVE_PRICES, gen_model="g", critic_model="k", campaign_id="X", caller=Caller("o", "a"),
                                source_commit="x", out_dir=Path(tmp), topic_ids=("N01", "N07"), strata=pilot.PILOT_STRATA)

    def test_conditions_differ_only_by_the_declared_policy(self):
        rows = pilot.conditions_report(corp.load_corpus())
        self.assertEqual([r["topic_id"] for r in rows], sorted(corp.PILOT_IDS))
        for r in rows:
            self.assertEqual(r["split"], "pilot")
            self.assertEqual(r["policy_diff"], ["standard.structure", "standard.policy_addendum"])
            self.assertNotEqual(r["A_prompt_sha256"], r["B_prompt_sha256"])
        self.assertEqual(len({r["user_sha256"] for r in rows}), 5)     # un message utilisateur par sujet, identique entre A et B (vérifié ci-dessus)

    def test_a_drifting_b_prompt_is_refused(self):
        original = policy.build_condition

        def drifting(stratum, condition, view, manifest=None):
            spec = original(stratum, condition, view, manifest)
            if condition == "B":
                spec = {**spec, "system": spec["system"] + " Consigne ajoutée hors diff déclaré."}   # B qui dérive de « A + diff déclaré »
            return spec
        try:
            policy.build_condition = drifting
            with self.assertRaises(AssertionError):
                pilot.conditions_report(corp.load_corpus())
        finally:
            policy.build_condition = original
        pilot.conditions_report(corp.load_corpus())          # restauré : de nouveau cohérent


class TestRehearsal(NetworkBlocked):
    def test_dry_run_is_complete_offline_and_within_the_call_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = rehearsal(tmp)
            s = out["summary"]
            self.assertEqual((s["mode"], s["strata"], s["logical_calls_total"]), ("offline_simulation", ["standard"], 20))
            self.assertEqual((s["logical_calls"]["generation"], s["logical_calls"]["critique"]), (10, 10))
            self.assertEqual((s["network"]["attempts_blocked"], s["halted_on_hidden_retry"]), (0, False))
            self.assertEqual(len(out["generator_requests"]), 10)
            self.assertTrue(all('{"blocks"' in r["system"] for r in out["generator_requests"]))      # aucune requête Story Visual
            self.assertTrue(all(r["http_attempts"] in (1, "1") for r in out["rows"] if r["logical_calls"] not in (0, "")))  # aucun retry caché

    def test_nothing_outside_the_five_subjects_or_evaluator_only_is_ever_sent(self):
        corpus = corp.load_corpus()
        with tempfile.TemporaryDirectory() as tmp:
            out = rehearsal(tmp)
        sent = "\n".join(json.dumps(r, ensure_ascii=False) for r in out["generator_requests"] + out["critic_requests"])
        for tid, topic in corpus["topics"].items():
            for text in corp._leaf_strings(topic["evaluator_only"]):
                if len(text) >= 12:
                    self.assertNotIn(text, sent, tid)
            if topic["split"] != "pilot":
                self.assertNotIn(topic["generator_input"]["brief"], sent, tid)
                self.assertNotIn(topic["generator_input"]["topic"], sent, tid)

    def test_audit_dossier_is_complete_and_the_plan_is_written_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = rehearsal(tmp)
            root = Path(tmp)
            manifest = json.loads((root / "campaign_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual((manifest["strata"], manifest["limits"]["max_logical_calls"], manifest["limits"]["retries"]), (["standard"], 20, 0))
            self.assertEqual(sorted(manifest["topics"]), sorted(corp.PILOT_IDS))
            self.assertEqual(manifest["allowed_splits"], ["pilot"])
            self.assertEqual(manifest["baseline_manifest"]["standard"]["source_commit"], "c61480d6")
            self.assertEqual(manifest["prices"]["generation"]["source"], pilot.ILLUSTRATIVE_PRICES.source)   # tarif fictif, étiqueté comme tel
            self.assertNotIn("api_key", json.dumps(manifest).lower())
            inputs = sorted((root / "inputs").glob("B*.json"))
            self.assertEqual(len(inputs), 10)
            for path in inputs:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(corp.sha256_text(data["system"] + "\n---\n" + data["user"]), data["prompt_sha256"])
            self.assertEqual(len(list(root.glob("B*.json"))), 10)               # sorties brutes, jamais réparées
            rows = list(csv.DictReader(io.StringIO((root / "registre_executions.csv").read_text(encoding="utf-8"))))
            self.assertEqual(len(rows), 20)
            self.assertTrue(all(r["observed_cost"] == "" for r in rows))        # jamais de « facture observée » inventée
            self.assertTrue(all(r["estimated_cost"] != "" for r in rows))        # estimation tarifée présente (tarif fictif de répétition)
            self.assertEqual(len({(r["model"], r["model_config"]) for r in rows if r["task"] == "generation"}), 1)   # mêmes réglages A et B
            self.assertTrue((root / "pilot_preparation.json").is_file())

    def test_the_rehearsal_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            rehearsal(t1)
            rehearsal(t2)
            names = sorted(p.relative_to(t1).as_posix() for p in Path(t1).rglob("*") if p.is_file())
            self.assertEqual(names, sorted(p.relative_to(t2).as_posix() for p in Path(t2).rglob("*") if p.is_file()))
            self.assertEqual(len(names), 24)   # manifeste de campagne, journal, rapport, préparation + 10 entrées + 10 sorties brutes
            for name in names:
                self.assertEqual((Path(t1) / name).read_bytes(), (Path(t2) / name).read_bytes(), name)


class TestProjection(NetworkBlocked):
    def test_projection_is_labelled_an_estimate_and_never_invents_a_price(self):
        rows = pilot.conditions_report(corp.load_corpus())
        none = pilot.projected_usage(rows)
        self.assertEqual((none["kind"], none["usd"], none["cases"]), ("ESTIMATE_NOT_MEASUREMENT", None, 10))
        self.assertEqual(none["tokens_ceiling"]["logical_calls"], 20)
        lo, hi = none["tokens_expected"]["input"]
        self.assertTrue(0 < lo < hi < none["tokens_ceiling"]["input"])
        priced = pilot.projected_usage(rows, Prices(1.0, 4.0, source="test"))["usd"]
        self.assertTrue(0 < priced["expected_low"] < priced["expected_high"] < priced["ceiling"])


if __name__ == "__main__":
    unittest.main()
