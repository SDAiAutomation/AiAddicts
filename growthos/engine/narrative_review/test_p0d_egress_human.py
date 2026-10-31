"""Prérequis P0-D 1/5/6 : coupure réseau OS (logique pure, état de pare-feu SIMULÉ au format réel), checklist des sources, protocole d'évaluation à l'aveugle."""
from __future__ import annotations

import copy
import csv
import io
import ipaddress
import json
import random
import tempfile
import unittest
from pathlib import Path

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.harness import corpus as corp
from growthos.engine.narrative_review.harness import runner
from growthos.engine.narrative_review.p0d import egress as eg
from growthos.engine.narrative_review.p0d import evaluation as ev
from growthos.engine.narrative_review.p0d import source_validation as sv

PLAN = eg.EgressPlan(campaign_id="P0D-TEST", harness_program=r"C:\Python311\python.exe", broker_program=r"C:\p0d\broker\python.exe",
                     provider_host="api.provider-example.com", provider_ips=("8.8.4.4", "9.9.9.9", "2001:4860:4860::8844"),
                     window_end_iso="2026-11-03T21:00:00+00:00")
REAL_FORMAT = ('{"Name":"NETDIS-UPnPHost-Out-TCP","DisplayName":"Découverte de réseau (UPnP-Sortie)","Enabled":"False","Direction":"Outbound","Action":"Allow",'
               '"Program":"%SystemRoot%\\\\system32\\\\svchost.exe","RemoteAddress":["LocalSubnet"],"Protocol":"TCP","RemotePort":["2869"]}')


def simulated_state(plan=PLAN):
    return [{"Name": r["name"], "DisplayName": r["name"], "Enabled": "True", "Direction": "Outbound", "Action": r["action"], "Program": r["program"],
             "RemoteAddress": r["remote"], "Protocol": r["protocol"], "RemotePort": r["port"]} for r in eg._rules(plan)]


def attest(state, plan=PLAN):
    return eg.attest(plan, eg.parse_firewall_state(json.dumps(state)))


class TestComplementCoverage(unittest.TestCase):
    def test_the_complement_covers_everything_except_the_allowed_addresses_with_no_overlap(self):
        rng = random.Random(7)
        for _ in range(60):
            v4 = {str(ipaddress.IPv4Address(rng.randrange(2**32))) for _ in range(rng.randint(1, 6))}
            v6 = {str(ipaddress.IPv6Address(rng.randrange(2**128))) for _ in range(rng.randint(0, 3))}
            allowed = sorted(v4 | v6)
            ranges = eg.complement_ranges(allowed)
            for version, top in ((4, 2**32 - 1), (6, 2**128 - 1)):
                spans = sorted([(int(ipaddress.ip_address(a)), int(ipaddress.ip_address(b))) for a, b in ranges if ipaddress.ip_address(a).version == version]
                               + [(int(ipaddress.ip_address(ip)),) * 2 for ip in allowed if ipaddress.ip_address(ip).version == version])
                cursor = 0
                for start, end in spans:
                    self.assertEqual(start, cursor)       # ni trou ni chevauchement
                    cursor = end + 1
                self.assertEqual(cursor, top + 1)

    def test_edges_of_the_address_space(self):
        self.assertEqual(eg.complement_ranges(["0.0.0.0"])[0], ("0.0.0.1", "255.255.255.255"))
        self.assertEqual(eg.complement_ranges(["255.255.255.255"])[0], ("0.0.0.0", "255.255.255.254"))
        self.assertEqual(len(eg.complement_ranges(["1.2.3.4", "1.2.3.5"])), 2 + 1)         # deux IPv4 adjacentes : une plage avant, une après (+ tout l'IPv6)


class TestPlanAndScripts(unittest.TestCase):
    def test_plan_validation(self):
        self.assertEqual(PLAN.validate(), [])
        bad = [dict(campaign_id="a b"), dict(harness_program="python.exe"), dict(harness_program=r"C:\x\py.exe; calc"), dict(broker_program=r"C:\Python311\PYTHON.EXE"),
               dict(provider_ips=()), dict(provider_ips=("10.0.0.1",)), dict(provider_ips=("127.0.0.1",)), dict(provider_ips=("not-an-ip",)), dict(provider_ips=("0.0.0.0",)),
               dict(provider_ips=("169.254.1.1",)), dict(window_end_iso="tomorrow")]
        for over in bad:
            plan = eg.EgressPlan(**{**PLAN.__dict__, **over})
            self.assertTrue(plan.validate(), over)
            with self.assertRaises(c.ReviewError):
                eg.open_script(plan)

    def test_the_open_script_only_blocks_and_expires(self):
        script = eg.open_script(PLAN)
        self.assertNotIn("-Action Allow", script)
        self.assertEqual(script.count("-Action Block"), len(eg._rules(PLAN)))
        self.assertIn("-Direction Outbound", script)
        self.assertIn(PLAN.broker_program, script)
        self.assertIn("Register-ScheduledTask", script)             # expiration automatique des règles du courtier
        self.assertIn("8.8.4.4", script)                       # les IP du fournisseur figurent dans le blocage des ports (jamais dans une règle d'autorisation)
        harness_rule = next(r for r in eg._rules(PLAN) if "HARNESS" in r["name"])
        self.assertTrue(harness_rule["permanent"])
        self.assertEqual(harness_rule["remote"], ["Any"])
        close = eg.close_script(PLAN)
        self.assertIn("Remove-NetFirewallRule", close)
        self.assertNotIn("HARNESS-BLOCK-ALL", close)                # le blocage du harness reste

    def test_the_verify_script_is_read_only(self):
        script = eg.verify_script(PLAN)
        for forbidden in ("New-", "Remove-", "Set-", "Enable-", "Disable-", "Register-", "Start-", "Invoke-", "netsh"):
            self.assertNotIn(forbidden, script)
        self.assertIn("Get-NetFirewallRule", script)

    def test_the_external_probe_targets_documentation_space_only(self):
        for role, exe in (("harness", PLAN.harness_program), ("broker", PLAN.broker_program)):
            cmd = eg.probe_command(PLAN, role)
            self.assertIn(exe, cmd)
            self.assertIn("192.0.2.1", cmd)
            self.assertTrue(ipaddress.ip_address(eg.PROBE_TARGET) in ipaddress.ip_network("192.0.2.0/24"))


class TestAttestation(unittest.TestCase):
    def test_a_correct_firewall_state_is_attested_and_the_digest_is_stable(self):
        a1, a2 = attest(simulated_state()), attest(list(reversed(simulated_state())))
        self.assertEqual((a1.ok, a1.problems), (True, ()))
        self.assertEqual(a1.sha256, a2.sha256)                                  # l'ordre de lecture ne change pas l'empreinte
        self.assertRegex(a1.sha256, r"^[0-9a-f]{64}$")
        self.assertNotEqual(a1.sha256, attest(simulated_state(), eg.EgressPlan(**{**PLAN.__dict__, "window_end_iso": "2026-11-04T21:00:00+00:00"})).sha256)

    def test_every_drift_from_the_plan_is_reported(self):
        def mutate(fn):
            state = simulated_state()
            fn(state)
            return attest(state)
        cases = {
            "rule disabled": lambda s: s[0].update(Enabled="False"),
            "harness block missing": lambda s: s.remove(next(r for r in s if "HARNESS" in r["Name"])),
            "coverage hole": lambda s: s.remove(next(r for r in s if "OUTSIDE-02" in r["Name"])),
            "wrong program": lambda s: next(r for r in s if "HARNESS" in r["Name"]).update(Program=r"C:\other\python.exe"),
            "udp rule missing": lambda s: s.remove(next(r for r in s if "UDP" in r["Name"])),
            "ports rule changed": lambda s: next(r for r in s if "OTHER-PORTS" in r["Name"]).update(RemotePort=["Any"]),
            "action flipped": lambda s: next(r for r in s if "OUTSIDE-01" in r["Name"]).update(Action="Allow"),
            "unexpected campaign rule": lambda s: s.append({**s[0], "Name": "P0D-P0D-TEST-EXTRA"}),
            "allow rule for the broker": lambda s: s.append({**s[0], "Name": "Some-Other-Allow", "Action": "Allow", "Program": PLAN.broker_program.lower()}),
            "allow rule for the harness": lambda s: s.append({**s[0], "Name": "Browser-Allow", "Action": "Allow", "Program": PLAN.harness_program}),
        }
        for label, fn in cases.items():
            result = mutate(fn)
            self.assertFalse(result.ok, label)
            self.assertTrue(result.problems, label)

    def test_overlapping_or_widened_coverage_is_a_problem_too(self):
        state = simulated_state()
        outside = next(r for r in state if "OUTSIDE-01" in r["Name"])
        start, end = outside["RemoteAddress"][0].split("-")
        outside["RemoteAddress"] = [f"{start}-{ipaddress.IPv4Address(int(ipaddress.IPv4Address(end)) + 1)}"]        # avale la première IP autorisée
        self.assertFalse(attest(state).ok)

    def test_an_allow_rule_that_is_disabled_or_inbound_is_not_a_hole(self):
        state = simulated_state()
        state.append({**state[0], "Name": "Disabled-Allow", "Action": "Allow", "Program": PLAN.broker_program, "Enabled": "False"})
        state.append({**state[0], "Name": "Inbound-Allow", "Action": "Allow", "Program": PLAN.broker_program, "Direction": "Inbound"})
        self.assertTrue(attest(state).ok)

    def test_real_get_netfirewallrule_output_parses_and_malformed_output_is_an_error(self):
        parsed = eg.parse_firewall_state(REAL_FORMAT)
        self.assertEqual((parsed[0]["name"], parsed[0]["enabled"], parsed[0]["action"], parsed[0]["remote"], parsed[0]["port"]),
                         ("NETDIS-UPnPHost-Out-TCP", False, "Allow", ["LocalSubnet"], ["2869"]))
        self.assertEqual(eg.parse_firewall_state("[]"), [])
        self.assertEqual(eg.parse_firewall_state("null"), [])
        for bad in ('[{"Name": "x"}]', '["x"]', "not json"):
            with self.assertRaises((ValueError, KeyError)):
                eg.parse_firewall_state(bad)

    def test_an_empty_firewall_never_attests(self):
        self.assertFalse(attest([]).ok)

    def test_live_attestation_reads_through_an_injected_read_only_runner(self):
        seen = []

        def runner_(script):
            seen.append(script)
            return json.dumps(simulated_state())
        result = eg.live_attestation(PLAN, runner_)
        self.assertTrue(result.ok)
        self.assertEqual(seen, [eg.verify_script(PLAN)])                         # elle n'exécute QUE le script de lecture
        self.assertEqual(result.sha256, attest(simulated_state()).sha256)


class TestSourceChecklist(unittest.TestCase):
    def setUp(self):
        self.corpus = corp.load_corpus()
        self.template = sv.build_checklist(self.corpus)

    def filled(self):
        rec = copy.deepcopy(self.template)
        rec["status"] = "FILLED_BY_HUMAN"
        rec["verifier"] = {"name": "Relecteur Exemple", "role": "relecteur externe", "independent_of_authors": True, "signed_on": "2026-11-02"}
        for src in rec["sources"]:
            for check in src["checks"].values():
                check["state"] = "verified"
            for claim in src["claims"]:
                claim.update(state="verified", page_quote="Citation textuelle de la page, assez longue.", checked_on="2026-11-02")
            src["decision"] = "human_verified"
        return rec

    def test_only_the_documentary_pilot_subject_needs_human_validation(self):
        self.assertEqual(sv.required_source_ids(self.corpus), ["S01", "S02"])
        self.assertEqual([s["source_id"] for s in self.template["sources"]], ["S01", "S02"])

    def test_the_template_declares_nothing_verified_and_matches_the_committed_file(self):
        self.assertEqual(self.template["status"], "TEMPLATE_NOT_VERIFIED")
        self.assertEqual(self.template["verifier"], {"name": None, "role": None, "independent_of_authors": None, "signed_on": None})
        states = [self.template["sources"][i]["claims"][j]["state"] for i in range(2) for j in range(len(self.template["sources"][i]["claims"]))]
        self.assertTrue(states and set(states) == {"unverified"})
        self.assertTrue(all(ch["state"] == "unverified" for s in self.template["sources"] for ch in s["checks"].values()))
        committed = json.loads((corp.FIXTURES / "p0d" / "source_validation_S01_S02.template.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, self.template)
        # le corpus lui-même n'a JAMAIS été déclaré vérifié par cet outil
        self.assertTrue(all(s["verification"] != "human_verified" and not s["human_verified_by"] for s in self.corpus["sources"].values()))

    def test_the_blank_template_is_not_a_valid_record(self):
        self.assertGreater(len(sv.validate_record(self.template, self.corpus)), 5)

    def test_a_complete_independent_record_is_structurally_valid_but_changes_nothing(self):
        before = copy.deepcopy(self.corpus["sources"])
        self.assertEqual(sv.validate_record(self.filled(), self.corpus), [])
        self.assertEqual(self.corpus["sources"], before)

    def test_incomplete_or_inconsistent_records_are_rejected(self):
        def problems(fn):
            rec = self.filled()
            fn(rec)
            return sv.validate_record(rec, self.corpus)
        cases = {
            "not independent": lambda r: r["verifier"].update(independent_of_authors=False),
            "no name": lambda r: r["verifier"].update(name=""),
            "bad date": lambda r: r["verifier"].update(signed_on="hier"),
            "wrong corpus version": lambda r: r.update(sources_sha256="0" * 64),
            "missing source": lambda r: r["sources"].pop(),
            "claim undecided": lambda r: r["sources"][0]["claims"][0].update(state="unverified"),
            "verified without quote": lambda r: r["sources"][0]["claims"][0].update(page_quote=None),
            "quote too long": lambda r: r["sources"][0]["claims"][0].update(page_quote="x" * 301),
            "no check date": lambda r: r["sources"][0]["claims"][0].update(checked_on=None),
            "check undecided": lambda r: next(iter(r["sources"][0]["checks"].values())).update(state="unverified"),
            "summary edited": lambda r: r["sources"][0]["claims"][0].update(summary_sentence="Phrase réécrite."),
            "human_verified with a failed claim": lambda r: r["sources"][1]["claims"][0].update(state="not_supported"),
            "no decision": lambda r: r["sources"][0].update(decision=None),
            "unknown state": lambda r: r["sources"][0]["claims"][0].update(state="maybe"),
        }
        for label, fn in cases.items():
            self.assertTrue(problems(fn), label)

    def test_a_failed_source_can_be_recorded_honestly_as_needs_fix(self):
        rec = self.filled()
        rec["sources"][1]["claims"][0].update(state="not_supported", page_quote=None)
        rec["sources"][1]["decision"] = "needs_fix"
        self.assertEqual(sv.validate_record(rec, self.corpus), [])


def fake_manifest():
    cases = runner.plan_cases("EVAL", corp.PILOT_IDS, ("standard",))
    return {"campaign_id": "EVAL", "cases": cases}


class TestBlindEvaluation(unittest.TestCase):
    def setUp(self):
        self.corpus = corp.load_corpus()
        self.manifest = fake_manifest()

    def test_allocation_is_balanced_and_no_listener_hears_both_variants_of_a_topic(self):
        plan = ev.allocate()
        self.assertEqual(len(plan), 60)
        for listener in {p["listener"] for p in plan}:
            mine = [p for p in plan if p["listener"] == listener]
            self.assertEqual(sorted(p["topic_id"] for p in mine), sorted(corp.PILOT_IDS))          # un passage par sujet
            self.assertEqual(sorted(p["position"] for p in mine), [1, 2, 3, 4, 5])
        for topic in corp.PILOT_IDS:
            variants = [p["variant"] for p in plan if p["topic_id"] == topic]
            self.assertEqual((variants.count("A"), variants.count("B")), (6, 6))                    # 6 auditeurs par variante et par sujet
        orders = {tuple(p["topic_id"] for p in plan if p["listener"] == f"L{r:02d}") for r in range(1, 13)}
        self.assertGreater(len(orders), 5)                                                         # l'ordre des sujets tourne
        self.assertEqual(plan, ev.allocate())                                                      # déterministe

    def test_the_rubric_covers_the_five_requested_dimensions_with_anchored_levels(self):
        self.assertEqual(set(ev.RUBRIC), {"narrative_quality", "causality", "clarity", "payoff", "factuality"})
        for dim, spec in ev.RUBRIC.items():
            self.assertTrue(all(spec.get(level) for level in ("label", "1", "3", "5")), dim)

    def test_listener_facing_files_hold_opaque_ids_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            paths = ev.build_packets(self.manifest, self.corpus, out)
            public = {n: p.read_text(encoding="utf-8") for n, p in paths.items() if not n.startswith("PRIVATE")}
            self.assertEqual(set(public), {"listener_sheets.csv", "scores_template.csv", "pair_votes_template.csv", "recall_24h_template.csv"})
            secrets = list(corp.PILOT_IDS) + ["standard", "story_visual", "condition", "evaluator_only", "variant", "A_", "_B"]
            for tid, topic in self.corpus["topics"].items():
                for text in corp._leaf_strings(topic["evaluator_only"]):
                    secrets.append(text)
                secrets += [topic["generator_input"]["topic"]]
            for name, text in public.items():
                for secret in secrets:
                    self.assertNotIn(secret, text, (name, secret))
            self.assertEqual(len(list(csv.DictReader(io.StringIO(public["listener_sheets.csv"])))), 60)
            self.assertIn("narrative_quality", public["scores_template.csv"].splitlines()[0])
            key = json.loads((out / "PRIVATE_unblinding_key.json").read_text(encoding="utf-8"))
            self.assertIn("PRIVATE", key["WARNING"])
            self.assertEqual(len(key["blind_to_case"]), 10)
            self.assertEqual({v["condition"] for v in key["blind_to_case"].values()}, {"A", "B"})

    def test_pair_sides_are_mixed_and_every_listener_row_maps_to_a_blind_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev.build_packets(self.manifest, self.corpus, Path(tmp))
            key = json.loads((Path(tmp) / "PRIVATE_unblinding_key.json").read_text(encoding="utf-8"))
            pairs = list(csv.DictReader(io.StringIO((Path(tmp) / "pair_votes_template.csv").read_text(encoding="utf-8"))))
            self.assertEqual(len(pairs), 15)                                                       # 3 relecteurs x 5 paires
            sides = {key["blind_to_case"][p["left_blind_id"]]["condition"] for p in pairs}
            self.assertEqual(sides, {"A", "B"})                                                    # A n'est pas toujours à gauche
            sheets = list(csv.DictReader(io.StringIO((Path(tmp) / "listener_sheets.csv").read_text(encoding="utf-8"))))
            self.assertTrue(all(r["blind_script_id"] in key["blind_to_case"] for r in sheets))

    def test_aggregation_uses_medians_per_script_and_never_invents_missing_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            ev.build_packets(self.manifest, self.corpus, Path(tmp))
            key = json.loads((Path(tmp) / "PRIVATE_unblinding_key.json").read_text(encoding="utf-8"))
        blind = {(v["topic_id"], v["condition"]): k for k, v in key["blind_to_case"].items()}
        scores = []
        for topic in corp.PILOT_IDS:
            for cond, base in (("A", 2), ("B", 4)):
                for rater in range(3):
                    scores.append({"blind_script_id": blind[(topic, cond)], **{d: base + (rater == 0) for d in ev.RUBRIC}})
        diffs = ev.pair_differences(scores, key)
        self.assertTrue(all(not d["provisional"] and set(d["differences_B_minus_A"].values()) == {2.0} for d in diffs))
        thin = [s for s in scores if not (s["blind_script_id"] == blind[("N01", "B")] and s is not scores[3])]
        by_topic = {d["topic_id"]: d for d in ev.pair_differences(thin, key)}
        self.assertTrue(by_topic["N01"]["provisional"])
        self.assertTrue(all(v is None for v in by_topic["N01"]["differences_B_minus_A"].values()))   # manquant : jamais 0
        self.assertFalse(by_topic["N04"]["provisional"])


if __name__ == "__main__":
    unittest.main()

