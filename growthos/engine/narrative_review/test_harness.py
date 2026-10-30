"""P0-C : corpus, baseline figée, politique B, runner A/B, journal. Hors réseau ; fournisseurs factices ; aucun coût."""
from __future__ import annotations

import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import policy, runner
from growthos.engine.narrative_review.harness.offline import offline
from growthos.engine.narrative_review.harness.simulation import simulated_critic, simulated_generator
from growthos.engine.narrative_review.providers import Budget, Prices
from growthos.engine.narrative_review.reviewer import Caller
from growthos.engine.narrative_review.test_review import NetworkBlocked

PRICES = Prices(input_per_m=1.0, output_per_m=2.0, as_of="2026-10-30", source="test fixture")
CALLER = Caller("org-A", "acc-A")


def campaign(corpus=None, *, generator=None, critic=None, budget=None, gen_prices=PRICES, critic_prices=PRICES, out_dir=None, **kw):
    corpus = corpus or corp.load_corpus()
    return runner.run_campaign(
        corpus, generator=generator or simulated_generator(), critic=critic or simulated_critic(), budget=budget or Budget(5.0),
        gen_prices=gen_prices, critic_prices=critic_prices, gen_model="sim-gen", critic_model="sim-critic", campaign_id="T-1",
        caller=CALLER, source_commit="deadbeef", out_dir=out_dir, **kw)


class TestCorpus(NetworkBlocked):
    def test_twenty_topics_split_5_5_10_and_hashes(self):
        corpus = corp.load_corpus()
        self.assertEqual(len(corpus["topics"]), 20)
        splits = [t["split"] for t in corpus["topics"].values()]
        self.assertEqual((splits.count("pilot"), splits.count("development"), splits.count("holdout")), (5, 5, 10))
        self.assertEqual(sorted(t for t, v in corpus["topics"].items() if v["split"] == "pilot"), sorted(corp.PILOT_IDS))
        self.assertEqual(len(corpus["hashes"]["corpus_sha256"]), 64)

    def test_validation_rejects_bad_corpora(self):
        corpus = corp.load_corpus()
        raw = json.loads((corp.FIXTURES / "corpus_20.json").read_text(encoding="utf-8"))
        for mutate in (lambda d: d["topics"].pop(), lambda d: d["topics"][0].update(split="holdout"),
                       lambda d: d["topics"][0]["generator_input"].update(source_ids=["S99"]),
                       lambda d: d["topics"][0].pop("evaluator_only")):
            broken = copy.deepcopy(raw)
            mutate(broken)
            with self.assertRaises(corp.CorpusError):
                corp.validate_corpus(broken, corpus["sources"])

    def test_generator_view_never_carries_evaluator_only_and_refuses_other_splits(self):
        corpus = corp.load_corpus()
        view = corp.generator_view(corpus, "N01")
        self.assertNotIn("evaluator_only", json.dumps(view))
        for tid, topic in corpus["topics"].items():
            if topic["split"] != "pilot":
                with self.assertRaises(corp.HoldoutAccessError):
                    corp.generator_view(corpus, tid)

    def test_leak_guard_catches_evaluator_values_and_foreign_holdout_subjects(self):
        corpus = corp.load_corpus()
        secret = next(iter(corp._leaf_strings(corpus["topics"]["N01"]["evaluator_only"])))
        with self.assertRaises(corp.LeakError):
            corp.assert_no_leak("blabla " + secret, corpus)
        holdout = next(t for t in corpus["topics"].values() if t["split"] == "holdout")
        with self.assertRaises(corp.LeakError):
            corp.assert_no_leak(holdout["generator_input"]["brief"], corpus, own_topic_id="N01")
        corp.assert_no_leak(corp.generator_view(corpus, "N01")["generator_input"]["brief"], corpus, own_topic_id="N01")


class TestPolicy(NetworkBlocked):
    def setUp(self):
        super().setUp()
        self.corpus = corp.load_corpus()
        self.manifest = policy.load_manifest()

    def test_frozen_baselines_match_their_manifest_and_trace_to_commits(self):
        a = policy.frozen_standard_A(self.manifest)
        self.assertIn("Durée YouTube Shorts", a)          # plateforme du corpus consignée
        self.assertEqual(self.manifest["standard"]["source_commit"], "c61480d6")
        self.assertEqual(self.manifest["story_visual"]["source_commit"][:7], "57af0ae")
        self.assertEqual(len(self.manifest["standard"]["source_files_sha256"]), 5)
        bad = copy.deepcopy(self.manifest)
        bad["standard"]["rendered_sha256"] = "0" * 64
        with self.assertRaises(policy.BaselineError):
            policy.frozen_standard_A(bad)

    def test_b_differs_from_a_only_by_the_declared_policy_edits(self):
        a = policy.frozen_standard_A(self.manifest)
        b, diff = policy.standard_B(a)
        self.assertEqual([d["id"] for d in diff], ["standard.structure", "standard.policy_addendum"])
        self.assertNotIn("Structure narrative en 5 temps", b)
        self.assertNotIn("Preuve immédiate", b)
        self.assertIn("Structure narrative en 5 temps", a)
        self.assertIn(c.POLICY_VERSION, b)
        for kept in ("10 mots MAXIMUM", "12 mots maximum", 'Réponds uniquement en JSON valide', "Durée YouTube Shorts",
                     "Longueur des blocs", "Découpage visuel"):  # contrat technique et format conservés
            self.assertIn(kept, b, kept)
        # tout ce qui précède et suit le bloc de structure est identique à A
        start = a.index("Structure narrative en 5 temps")
        head, tail = a[:start], a[a.index("\n\nDurée ", start):]
        self.assertTrue(b.startswith(head))
        self.assertIn(tail.split("Réponds uniquement en JSON valide")[0], b)

    def test_visual_b_is_a_plus_addendum_and_keeps_six_beats(self):
        frozen = policy.frozen_visual_A("N01", self.manifest)
        b, diff = policy.visual_B(frozen["prompt"])
        self.assertTrue(b.startswith(frozen["prompt"]))
        self.assertEqual([d["id"] for d in diff], ["story_visual.policy_addendum"])
        self.assertIn("six beats", b)
        self.assertEqual(frozen["story_type"], "moral")

    def test_user_message_is_identical_across_conditions_and_free_of_evaluator_data(self):
        view = corp.generator_view(self.corpus, "N05")
        specs = {(s, cond): policy.build_condition(s, cond, view, self.manifest) for s in policy.STRATA for cond in policy.CONDITIONS}
        for s in policy.STRATA:
            self.assertEqual(specs[(s, "A")]["user"], specs[(s, "B")]["user"])
            self.assertNotEqual(specs[(s, "A")]["system"], specs[(s, "B")]["system"])
            self.assertEqual(specs[(s, "A")]["policy_diff"], [])
        self.assertIn("S01", specs[("standard", "A")]["user"])  # le dossier source accompagne les deux conditions
        for spec in specs.values():
            corp.assert_no_leak(spec["system"] + spec["user"], self.corpus, own_topic_id="N05")

    def test_policy_edit_that_no_longer_matches_fails_loudly(self):
        with self.assertRaises(policy.BaselineError):
            policy.standard_B("un prompt sans bloc de structure")


class TestRunner(NetworkBlocked):
    def test_twenty_cases_ten_pairs_forty_logical_calls_max(self):
        gen, crit = simulated_generator(), simulated_critic()
        result = campaign(generator=gen, critic=crit)
        self.assertEqual(len(result["pairs"]), 10)
        self.assertEqual((len(gen.requests), len(crit.requests)), (20, 20))
        self.assertEqual(result["summary"]["logical_calls_total"], 40)
        self.assertEqual(len(result["rows"]), 40)
        self.assertEqual(result["summary"]["mode"], "offline_simulation")
        self.assertTrue(all(p["A"]["blind_script_id"] != p["B"]["blind_script_id"] for p in result["pairs"]))
        blind = [r["blind_script_id"] for r in result["rows"] if r["task"] == "generation"]
        self.assertEqual(len(set(blind)), 20)

    def test_no_leak_in_any_outgoing_request(self):
        corpus = corp.load_corpus()
        gen, crit = simulated_generator(), simulated_critic()
        campaign(corpus, generator=gen, critic=crit)
        sent = "\n".join(json.dumps(r, ensure_ascii=False) for r in gen.requests + crit.requests)
        for tid, topic in corpus["topics"].items():
            for text in corp._leaf_strings(topic["evaluator_only"]):
                if len(text) >= 12:
                    self.assertNotIn(text, sent, tid)
            if topic["split"] != "pilot":
                self.assertNotIn(topic["generator_input"]["brief"], sent, tid)  # aucun sujet de développement/réserve

    def test_critic_never_sees_condition_tenant_or_subject_ids(self):
        crit = simulated_critic()
        campaign(critic=crit)
        for request in crit.requests:
            for forbidden in ("org-A", "acc-A", '"condition"', "blind_script_id", "evaluator", "T-1"):
                self.assertNotIn(forbidden, request["prompt"])

    def test_failures_are_logged_never_retried_and_cost_unknown_is_empty(self):
        gen = simulated_generator(fail_on={2}, no_output_on={3}, invalid_json_on={4})
        result = campaign(generator=gen)
        self.assertEqual(len(gen.requests), 20)           # une tentative par case : aucun retry
        statuses = [r["execution_status"] for r in result["rows"] if r["task"] == "generation"]
        self.assertEqual((statuses[1], statuses[2], statuses[3]), ("provider_error", "no_output", "ok"))
        row_fail = [r for r in result["rows"] if r["execution_status"] == "provider_error"][0]
        self.assertEqual((row_fail["estimated_cost"], row_fail["observed_cost"], row_fail["http_attempts"]), ("", "", ""))
        invalid = [r for r in result["rows"] if r["task"] == "generation" and r["technical_valid"] is False]
        self.assertEqual(len(invalid), 1)
        crit_rows = [r for r in result["rows"] if r["task"] == "critique"]
        self.assertEqual(len(crit_rows), 20 - 3)          # pas de critique pour une sortie inexploitable ou absente
        self.assertEqual(result["summary"]["costs"]["observed_usd"], None)
        self.assertGreaterEqual(result["summary"]["costs"]["attempts_with_unknown_cost"], 1)

    def test_critic_failure_is_one_attempt_and_visible(self):
        crit = simulated_critic(fail_on={1}, invalid_on={2})
        result = campaign(critic=crit)
        self.assertEqual(len(crit.requests), 20)
        crit_rows = [r for r in result["rows"] if r["task"] == "critique"]
        self.assertEqual((crit_rows[0]["error_code"], crit_rows[0]["editorial_decision"]), (c.PROVIDER_UNAVAILABLE, "review"))
        self.assertEqual((crit_rows[1]["error_code"], crit_rows[1]["execution_status"]), (c.INVALID_RESPONSE, "invalid"))

    def test_unknown_prices_or_tiny_budget_means_no_paid_call(self):
        for kwargs in ({"gen_prices": None, "critic_prices": None}, {"budget": Budget(0.0001)}):
            gen, crit = simulated_generator(), simulated_critic()
            result = campaign(generator=gen, critic=crit, **kwargs)
            self.assertEqual((len(gen.requests), len(crit.requests)), (0, 0))
            self.assertTrue(all(r["execution_status"] == "not_run" and r["error_code"] == c.BUDGET_EXHAUSTED for r in result["rows"]))

    def test_holdout_or_development_topics_cannot_enter_a_pilot_campaign(self):
        with self.assertRaises(corp.HoldoutAccessError):
            campaign(topic_ids=("N01", "N07"))

    def test_registry_matches_the_specified_columns_and_is_written_with_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = campaign(out_dir=Path(tmp))
            text = (Path(tmp) / "registre_executions.csv").read_text(encoding="utf-8")
            spec_header = (corp.FIXTURES / "registre_executions.header.csv").read_text(encoding="utf-8").strip().split(",")
            self.assertEqual(next(csv.reader(io.StringIO(text))), spec_header)
            report = json.loads((Path(tmp) / "campaign_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["baseline"]["standard_commit"], "c61480d6")
            self.assertEqual(report["corpus_sha256"], result["summary"]["corpus_sha256"])
            self.assertEqual(len(list(Path(tmp).glob("B*.json"))), 20)   # sorties brutes conservées telles quelles

    def test_a_is_traceable_and_b_prompts_differ_only_in_policy(self):
        result = campaign()
        gens = [r for r in result["rows"] if r["task"] == "generation"]
        by_pair = {}
        for r in gens:
            by_pair.setdefault((r["topic_id"], r["stratum"]), {})[r["condition"]] = r["prompt_hash"]
        self.assertTrue(all(v["A"] != v["B"] for v in by_pair.values()))
        self.assertTrue(all(r["prompt_version"] in ("c61480d6", policy.load_manifest()["story_visual"]["source_commit"]) for r in gens))

    def test_blind_ids_are_deterministic_per_campaign_and_do_not_leak_the_order(self):
        a, b = runner.plan_cases("T-1"), runner.plan_cases("T-1")
        self.assertEqual(a, b)
        self.assertNotEqual([x["blind_script_id"] for x in a], [x["blind_script_id"] for x in runner.plan_cases("T-2")])
        ordered = [x["blind_script_id"] for x in a]
        self.assertNotEqual(ordered, sorted(ordered))      # l'ordre des ID ne suit pas l'ordre sujet/condition


class TestHardeningFromIndependentReview(NetworkBlocked):
    def test_a_harness_error_is_journaled_and_the_campaign_goes_on(self):
        from growthos.engine.narrative_review.providers import ProviderResult
        base = simulated_generator()

        def duplicate_scene_ids(request):  # sortie techniquement valide dont l'instantané est refusé (ids de scène en double)
            result = base(request)
            if '{"blocks"' in request["system"]:
                return result
            data = json.loads(result.text)
            for scene in data["scenes"]:
                scene["id"] = "dup"
            return ProviderResult(text=json.dumps(data), usage=result.usage, latency_s=result.latency_s)
        with tempfile.TemporaryDirectory() as tmp:
            result = campaign(generator=offline(duplicate_scene_ids), out_dir=Path(tmp))
            lines = list(csv.DictReader(io.StringIO((Path(tmp) / "registre_executions.csv").read_text(encoding="utf-8"))))
        errors = [r for r in result["rows"] if r["execution_status"] == "harness_error"]
        self.assertEqual(len(errors), 10)                       # les 10 cases Story Visual
        self.assertEqual(len(lines), len(result["rows"]))      # tout ce qui a été journalisé est dans le fichier
        self.assertEqual(sum(r["task"] == "generation" for r in result["rows"]), 20)  # les 20 appels payés sont tous enregistrés
        self.assertEqual(sum(r["task"] == "critique" for r in result["rows"]), 10)

    def test_a_hidden_retry_halts_the_campaign(self):
        from growthos.engine.narrative_review.providers import ProviderResult
        inner = simulated_generator()
        count = {"n": 0}

        def retrying(request):
            count["n"] += 1
            result = inner(request)
            return ProviderResult(text=result.text, usage=result.usage, latency_s=1.0, http_attempts=2 if count["n"] == 3 else 1)
        result = campaign(generator=offline(retrying))
        self.assertEqual(count["n"], 3)                          # plus aucun appel après la détection
        self.assertTrue(result["summary"]["halted_on_hidden_retry"])
        self.assertEqual(sum(r["error_code"] == "HALTED_RETRY_DETECTED" for r in result["rows"]), 17)

    def test_critique_call_counter_matches_the_journal(self):
        crit = simulated_critic()
        result = campaign(critic=crit, budget=Budget(0.05))  # plafond trop bas pour les critiques : refus = 0 appel
        logged = sum(int(r["logical_calls"] or 0) for r in result["rows"] if r["task"] == "critique")
        self.assertEqual(result["summary"]["logical_calls"]["critique"], logged)
        self.assertEqual(len(crit.requests), logged)


if __name__ == "__main__":
    unittest.main()
