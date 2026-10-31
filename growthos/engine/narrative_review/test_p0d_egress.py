"""Prérequis P0-D 1 (revu après le contre-audit Codex) : coupure réseau OS, courtier BLOQUÉ PAR DÉFAUT. Logique pure sur des états de pare-feu SIMULÉS au format réel ; rien n'est appliqué."""
from __future__ import annotations

import ipaddress
import json
import random
from datetime import datetime, timedelta, timezone
import unittest

from growthos.engine.narrative_review import contract as c
from growthos.engine.narrative_review.p0d import egress as eg

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
PLAN = eg.EgressPlan(campaign_id="P0D-TEST", harness_program=r"C:\Python311\python.exe", broker_program=r"C:\p0d\broker\python.exe",
                     provider_host="api.provider-example.com", provider_ips=("8.8.4.4", "9.9.9.9", "2001:4860:4860::8844"),
                     window_end_iso="2026-11-03T21:00:00+00:00")
REAL_FORMAT = ('{"Name":"NETDIS-UPnPHost-Out-TCP","DisplayName":"Découverte de réseau (UPnP-Sortie)","Enabled":"False","Direction":"Outbound","Action":"Allow","Profile":"Any",'
               '"Program":"%SystemRoot%\\\\system32\\\\svchost.exe","RemoteAddress":["LocalSubnet"],"Protocol":"TCP","RemotePort":["2869"]}')


def to_state(rules):
    """Règles du plan -> JSON au format RÉEL de Get-NetFirewallRule (après analyse, comme le ferait `parse_firewall_state`)."""
    return [{"Name": r["name"], "DisplayName": r["name"], "Enabled": "True", "Direction": "Outbound", "Action": r["action"], "Profile": "Any", "Program": r["program"],
             "RemoteAddress": r["remote"], "Protocol": r["protocol"], "RemotePort": r["port"]} for r in rules]


def simulated(state="rest", plan=PLAN):
    return to_state(eg.rules_for_state(plan, state))


def attest(items, plan=PLAN, expect="rest"):
    return eg.attest(plan, eg.parse_firewall_state(json.dumps(items)), expect=expect)


def broker_ok(rules, plan=PLAN):
    return eg.reach_within_provider(plan, rules)


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
        self.assertEqual(len(eg.complement_ranges(["1.2.3.4", "1.2.3.5"])), 2 + 1)


class TestPlanAndScripts(unittest.TestCase):
    def test_plan_validation(self):
        self.assertEqual(PLAN.validate(), [])
        bad = [dict(campaign_id="a b"), dict(harness_program="python.exe"), dict(harness_program=r"C:\x\py.exe; calc"), dict(broker_program=r"C:\Python311\PYTHON.EXE"),
               dict(provider_ips=()), dict(provider_ips=("10.0.0.1",)), dict(provider_ips=("127.0.0.1",)), dict(provider_ips=("not-an-ip",)), dict(provider_ips=("0.0.0.0",)),
               dict(provider_ips=("169.254.1.1",)), dict(provider_ips=("224.0.0.1",)), dict(window_end_iso="tomorrow")]
        for over in bad:
            plan = eg.EgressPlan(**{**PLAN.__dict__, **over})
            self.assertTrue(plan.validate(), over)
            for script in (eg.install_script, eg.open_script, eg.close_script):
                with self.assertRaises(c.ReviewError):
                    script(plan)

    def test_no_script_creates_an_allow_rule_and_only_open_removes_a_rule_and_only_the_gate(self):
        for name, script in (("install", eg.install_script(PLAN)), ("open", eg.open_script(PLAN, now=NOW)), ("close", eg.close_script(PLAN))):
            self.assertNotIn("-Action Allow", script, name)
            self.assertNotIn("Allow", script.replace("AllowDown", ""), name)
        gate = eg.gate_rule(PLAN)["name"]
        removals = [line for line in eg.open_script(PLAN, now=NOW).splitlines() if "Remove-NetFirewallRule" in line]
        self.assertEqual(len(removals), 1)
        self.assertIn(gate, removals[0])                                         # le seul retrait de l'ouverture est le verrou
        for script in (eg.install_script(PLAN), eg.close_script(PLAN)):          # installation et fermeture ne retirent RIEN
            self.assertNotIn("Remove-NetFirewallRule", script)
            self.assertNotIn("Unregister-", script)

    def test_the_expiry_and_restart_task_only_adds_the_gate(self):
        task = eg._close_task(PLAN)
        self.assertIn("Register-ScheduledTask", task)
        self.assertIn("-AtStartup", task)                                        # reprise après redémarrage : le verrou est remis
        self.assertIn("2026-11-03T21:00:00+00:00", task)                         # et à l'expiration
        self.assertNotIn("Remove-", task)
        self.assertIn(eg.gate_rule(PLAN)["name"], task)
        open_script = eg.open_script(PLAN, now=NOW)
        self.assertLess(open_script.index("Register-ScheduledTask"), open_script.index("Remove-NetFirewallRule"))   # tâche enregistrée AVANT d'ouvrir

    def test_the_open_script_refuses_to_open_when_a_permanent_rule_is_missing(self):
        script = eg.open_script(PLAN, now=NOW)
        self.assertLess(script.index("throw"), script.index("Remove-NetFirewallRule"))
        for rule in eg.permanent_rules(PLAN):
            self.assertIn(rule["name"], script.split("Register-ScheduledTask")[0])

    def test_install_creates_the_atomic_complement_rule_first(self):
        steps = eg.install_steps(PLAN)
        self.assertTrue(steps[0][1]["name"].endswith("BROKER-BLOCK-OUTSIDE"))
        self.assertTrue(steps[-1][1]["name"].endswith("BROKER-BLOCK-GATE"))
        self.assertEqual(sum(1 for _, r in steps if "OUTSIDE" in r["name"]), 1)    # UNE règle, plusieurs plages : aucune installation à moitié couverte

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

    def test_uninstall_is_flagged_dangerous_and_is_never_part_of_a_campaign_script(self):
        self.assertIn("DANGER", eg.uninstall_script(PLAN))
        for script in (eg.install_script(PLAN), eg.open_script(PLAN, now=NOW), eg.close_script(PLAN)):
            self.assertNotIn(eg.uninstall_script(PLAN).splitlines()[0], script)


class TestDefaultBlocked(unittest.TestCase):
    """P1-1 : fermeture, expiration, erreur partielle ou redémarrage ne rendent JAMAIS au courtier un accès général."""

    def test_at_rest_the_broker_reaches_nothing_and_the_harness_never_reaches_anything(self):
        rest = eg.rules_for_state(PLAN, "rest")
        self.assertEqual(eg.reach(PLAN.broker_program, rest), [])
        self.assertEqual(eg.reach(PLAN.harness_program, rest, port=None, protocol="Any"), [])
        self.assertEqual(eg.reach(PLAN.broker_program, rest, port=None, protocol="UDP"), [])

    def test_while_open_the_broker_reaches_only_the_provider_ips(self):
        opened = eg.rules_for_state(PLAN, "open")
        got = eg.reach(PLAN.broker_program, opened)
        self.assertEqual(sorted((s, v) for s, e, v in got if s == e), sorted((s, v) for s, _e, v in eg.provider_span(PLAN)))
        self.assertTrue(eg.reach_within_provider(PLAN, opened))
        self.assertEqual(eg.reach(PLAN.broker_program, opened, port=80), [])       # pas le port 80 : seulement 443

    def test_every_prefix_of_install_open_and_close_keeps_the_broker_within_the_provider_ips(self):
        """Propriété centrale : à CHAQUE étape intermédiaire de chaque séquence (donc après une erreur partielle), l'accès du courtier est inclus dans les IP du fournisseur."""
        state = []
        for step in eg.install_steps(PLAN):
            state = eg.apply_step(state, step)
            self.assertTrue(broker_ok(state), f"after install step {step[1]['name']}")      # dès la 1re étape (la règle atomique), jamais plus que les IP du fournisseur
        self.assertEqual(eg.reach(PLAN.broker_program, state), [])
        for step in eg.open_steps(PLAN):
            state = eg.apply_step(state, step)
            self.assertTrue(broker_ok(state))
        after_open = state
        for step in eg.close_steps(PLAN):
            after_close = eg.apply_step(after_open, step)
            self.assertTrue(broker_ok(after_close))
            self.assertEqual(eg.reach(PLAN.broker_program, after_close), [])
        # l'enchaînement ouvrir/fermer/ouvrir, y compris des opérations répétées (idempotence) et rejouées après un redémarrage
        state = eg.rules_for_state(PLAN, "rest")
        for step in (eg.open_steps(PLAN) + eg.close_steps(PLAN) + eg.close_steps(PLAN) + eg.open_steps(PLAN) + eg.open_steps(PLAN) + eg.close_steps(PLAN)):
            state = eg.apply_step(state, step)
            self.assertTrue(broker_ok(state))
        self.assertEqual(eg.reach(PLAN.broker_program, state), [])

    def test_closing_never_removes_a_rule_so_no_failed_closing_can_widen_access(self):
        for op, rule in eg.close_steps(PLAN):
            self.assertEqual(op, "create")                                           # fermer = rajouter
        rest = eg.rules_for_state(PLAN, "rest")
        self.assertEqual(sorted(r["name"] for r in eg.apply_step(rest, eg.close_steps(PLAN)[0])), sorted(r["name"] for r in rest))   # idempotent

    def test_a_missing_or_disabled_permanent_rule_widens_the_reach_and_is_caught_by_the_attestation(self):
        for rule in eg.permanent_rules(PLAN):
            without = [r for r in eg.rules_for_state(PLAN, "rest") if r["name"] != rule["name"]]
            self.assertFalse(attest(to_state(without)).ok, rule["name"])
        disabled = to_state(eg.rules_for_state(PLAN, "rest"))
        next(r for r in disabled if "OUTSIDE" in r["Name"]).update(Enabled="False")
        result = attest(disabled)
        self.assertFalse(result.ok)
        self.assertTrue(any("can still reach" in p or "disabled" in p for p in result.problems))
        no_outside = [r for r in eg.rules_for_state(PLAN, "open") if "OUTSIDE" not in r["name"]]
        self.assertFalse(eg.reach_within_provider(PLAN, no_outside))                     # sans le complément, l'accès serait général


class TestAttestation(unittest.TestCase):
    def test_correct_rest_and_open_states_are_attested_and_the_digest_is_stable(self):
        rest, opened = attest(simulated("rest")), attest(simulated("open"), expect="open")
        self.assertEqual((rest.ok, rest.problems, opened.ok, opened.problems), (True, (), True, ()))
        self.assertEqual(rest.sha256, attest(list(reversed(simulated("rest")))).sha256)         # l'ordre de lecture ne change pas l'empreinte
        self.assertNotEqual(rest.sha256, opened.sha256)                                         # l'état attendu fait partie de l'empreinte
        self.assertRegex(rest.sha256, r"^[0-9a-f]{64}$")
        other = eg.EgressPlan(**{**PLAN.__dict__, "window_end_iso": "2026-11-04T21:00:00+00:00"})
        self.assertNotEqual(rest.sha256, attest(simulated("rest", other), other).sha256)

    def test_the_wrong_state_for_the_expectation_is_rejected(self):
        self.assertFalse(attest(simulated("open"), expect="rest").ok)           # verrou absent alors qu'on attend l'état au repos
        self.assertFalse(attest(simulated("rest"), expect="open").ok)           # verrou présent alors qu'on attend l'état ouvert

    def test_every_drift_from_the_plan_is_reported(self):
        def mutate(fn):
            state = simulated("rest")
            fn(state)
            return attest(state)
        cases = {
            "rule disabled": lambda s: s[0].update(Enabled="False"),
            "harness block missing": lambda s: s.remove(next(r for r in s if "HARNESS" in r["Name"])),
            "gate missing": lambda s: s.remove(next(r for r in s if "GATE" in r["Name"])),
            "complement widened": lambda s: next(r for r in s if "OUTSIDE" in r["Name"]).update(RemoteAddress=next(r for r in s if "OUTSIDE" in r["Name"])["RemoteAddress"][:-1]),
            "wrong program": lambda s: next(r for r in s if "HARNESS" in r["Name"]).update(Program=r"C:\other\python.exe"),
            "udp rule missing": lambda s: s.remove(next(r for r in s if "UDP" in r["Name"])),
            "ports rule changed": lambda s: next(r for r in s if "OTHER-PORTS" in r["Name"]).update(RemotePort=["Any"]),
            "action flipped": lambda s: next(r for r in s if "GATE" in r["Name"]).update(Action="Allow"),
            "unexpected campaign rule": lambda s: s.append({**s[0], "Name": "P0D-P0D-TEST-EXTRA"}),
            "allow rule for the broker": lambda s: s.append({**s[0], "Name": "Some-Other-Allow", "Action": "Allow", "Program": PLAN.broker_program.lower()}),
            "allow rule for the harness": lambda s: s.append({**s[0], "Name": "Browser-Allow", "Action": "Allow", "Program": PLAN.harness_program}),
        }
        for label, fn in cases.items():
            result = mutate(fn)
            self.assertFalse(result.ok, label)
            self.assertTrue(result.problems, label)

    def test_an_allow_rule_that_is_disabled_or_inbound_is_not_a_hole(self):
        state = simulated("rest")
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
        self.assertFalse(attest([], expect="open").ok)

    def test_live_attestation_reads_through_an_injected_read_only_runner(self):
        seen = []

        def runner_(script):
            seen.append(script)
            return json.dumps(simulated("rest"))
        result = eg.live_attestation(PLAN, runner_)
        self.assertTrue(result.ok)
        self.assertEqual(seen, [eg.verify_script(PLAN)])                         # elle n'exécute QUE le script de lecture
        self.assertEqual(result.sha256, attest(simulated("rest")).sha256)



class TestFirewallProfiles(unittest.TestCase):
    ON = [{"Name": n, "Enabled": "True", "DefaultOutboundAction": "Allow"} for n in ("Domain", "Private", "Public")]

    def test_the_profile_script_is_read_only(self):
        script = eg.profiles_script()
        for forbidden in ("New-", "Remove-", "Set-", "Enable-", "Disable-", "Register-", "Start-", "netsh"):
            self.assertNotIn(forbidden, script)
        self.assertIn("Get-NetFirewallProfile", script)

    def test_enabled_profiles_pass_and_any_disabled_or_missing_or_unreadable_profile_fails(self):
        self.assertEqual(eg.check_profiles(json.dumps(self.ON)), [])
        for name in ("Domain", "Private", "Public"):
            off = [{**p, "Enabled": "False"} if p["Name"] == name else p for p in self.ON]
            self.assertTrue(eg.check_profiles(json.dumps(off)), name)                    # un profil désactivé rend les règles inertes
            self.assertTrue(eg.check_profiles(json.dumps([p for p in self.ON if p["Name"] != name])), name)
        for bad in ("", "not json", "[]", "null", '[{"Name": "Domain"}]', "[1, 2]"):
            self.assertTrue(eg.check_profiles(bad), bad)

    def test_the_os_controller_never_attests_when_a_profile_is_off(self):
        def runner(on):
            profiles = self.ON if on else [{**p, "Enabled": "False"} if p["Name"] == "Public" else p for p in self.ON]
            return lambda script: json.dumps(profiles) if "Get-NetFirewallProfile" in script else json.dumps(simulated("rest"))
        self.assertTrue(eg.OsReadOnlyEgressController(PLAN, runner(True)).check("rest").ok)
        refused = eg.OsReadOnlyEgressController(PLAN, runner(False)).check("rest")
        self.assertFalse(refused.ok)
        self.assertTrue(any("public" in p for p in refused.problems))


if __name__ == "__main__":
    unittest.main()
