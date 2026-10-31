"""Coupure de sortie réseau au niveau du SYSTÈME D'EXPLOITATION pour la future campagne : PROPOSITION + générateurs + vérificateur d'état. Rien n'est appliqué ici.

Architecture à deux processus (le crochet CPython n'est qu'une première couche, contournable par du code natif) :
  - le processus de CAMPAGNE (interpréteur « harness ») : bloqué par le pare-feu pour TOUTE adresse distante, en permanence. La boucle locale n'est pas filtrée par le
    pare-feu Windows : il peut donc joindre un courtier local, et rien d'autre.
  - le COURTIER de transport (une COPIE de l'interpréteur, à un chemin dédié pour que la règle ne vise que lui) : seul programme autorisé à joindre le fournisseur. Comme un
    BLOCAGE l'emporte sur une AUTORISATION dans le pare-feu Windows, « seulement ces adresses » se code par le COMPLÉMENT : des règles de blocage couvrant tout l'espace
    d'adresses SAUF les IP du fournisseur (IPv4 et IPv6), plus un blocage de tous les ports sauf 443 vers ces IP, plus un blocage UDP total.
  - fenêtre : les règles de blocage du harness sont permanentes ; celles du courtier sont créées par `open_script` à l'ouverture et un `close_script` (plus une tâche
    planifiée d'expiration) les supprime. Hors fenêtre le courtier n'a pas d'accès non plus (aucune règle d'autorisation n'existe : il lui faut les IP pinées de la fenêtre).
Vérification indépendante de CPython : `verify_script` lit l'état RÉEL du pare-feu (lecture seule) ; `attest` le confronte au plan et produit une empreinte liée à l'autorisation ;
`live_attestation` la recalcule au démarrage de la campagne. Une sonde externe (`probe_command`, cible TEST-NET-1) permet au propriétaire de constater le blocage.

NON TESTÉ en conditions réelles : application des règles (droits d'administrateur requis), sonde, plateformes autres que Windows. Les tests couvrent la logique pure
(complément d'adresses, génération, analyse, attestation) sur des états de pare-feu simulés au format réel de `Get-NetFirewallRule`.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Callable

from .. import contract as c

RULE_PREFIX = "P0D"
PROBE_TARGET = "192.0.2.1"        # TEST-NET-1 (RFC 5737) : adresse de documentation, aucun serveur réel ne peut répondre
ALLOWED_PORT = 443


@dataclass(frozen=True)
class EgressPlan:
    campaign_id: str
    harness_program: str      # chemin complet de l'interpréteur de la campagne
    broker_program: str       # chemin complet de la COPIE dédiée de l'interpréteur (courtier)
    provider_host: str        # information : le courtier se connecte aux IP ci-dessous, avec ce nom pour SNI
    provider_ips: tuple[str, ...]   # IP du fournisseur relevées par le propriétaire à l'ouverture de la fenêtre
    window_end_iso: str       # fin de fenêtre : la tâche planifiée supprime les règles du courtier

    def validate(self) -> list[str]:
        problems = []
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", self.campaign_id):
            problems.append("campaign_id must be 3-40 letters, digits, '-' or '_'")
        for label, path in (("harness_program", self.harness_program), ("broker_program", self.broker_program)):
            if not re.fullmatch(r"[A-Za-z]:\\[^\"'`$;&|<>*?\r\n]+\.exe", path):
                problems.append(f"{label} must be a full Windows path to an .exe without shell metacharacters")
        if self.harness_program.lower() == self.broker_program.lower():
            problems.append("the broker must be a DEDICATED copy of the interpreter: a firewall rule on a shared path would also block or allow the harness")
        if not self.provider_ips:
            problems.append("provider_ips is empty: the broker would have no allowed destination")
        for ip in self.provider_ips:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                problems.append(f"invalid provider IP {ip!r}")
                continue
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved:
                problems.append(f"{ip} is not a public unicast address")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})", self.window_end_iso):
            problems.append("window_end_iso must be an ISO-8601 instant with a timezone")
        return problems


def complement_ranges(allowed_ips) -> list[tuple[str, str]]:
    """Plages (début, fin) couvrant TOUT l'espace d'adresses (IPv4 puis IPv6) sauf `allowed_ips`. Disjointes, triées, sans trou."""
    out: list[tuple[str, str]] = []
    for version, top in ((4, 2**32 - 1), (6, 2**128 - 1)):
        make = ipaddress.IPv4Address if version == 4 else ipaddress.IPv6Address
        values = sorted({int(ipaddress.ip_address(ip)) for ip in allowed_ips if ipaddress.ip_address(ip).version == version})
        cursor = 0
        for value in values:
            if value > cursor:
                out.append((str(make(cursor)), str(make(value - 1))))
            cursor = value + 1
        if cursor <= top:
            out.append((str(make(cursor)), str(make(top))))
    return out


def _range(r: tuple[str, str]) -> str:
    return f"{r[0]}-{r[1]}"


def _rules(plan: EgressPlan) -> list[dict]:
    """Règles voulues (source unique pour les scripts ET la vérification)."""
    p = RULE_PREFIX + "-" + plan.campaign_id
    rules = [{"name": f"{p}-HARNESS-BLOCK-ALL", "program": plan.harness_program, "action": "Block", "remote": ["Any"], "protocol": "Any", "port": ["Any"], "permanent": True},
             {"name": f"{p}-BROKER-BLOCK-UDP", "program": plan.broker_program, "action": "Block", "remote": ["Any"], "protocol": "UDP", "port": ["Any"], "permanent": False},
             {"name": f"{p}-BROKER-BLOCK-OTHER-PORTS", "program": plan.broker_program, "action": "Block", "remote": list(plan.provider_ips), "protocol": "TCP",
              "port": [f"1-{ALLOWED_PORT - 1}", f"{ALLOWED_PORT + 1}-65535"], "permanent": False}]
    for i, r in enumerate(complement_ranges(plan.provider_ips), 1):
        rules.append({"name": f"{p}-BROKER-BLOCK-OUTSIDE-{i:02d}", "program": plan.broker_program, "action": "Block", "remote": [_range(r)], "protocol": "Any", "port": ["Any"], "permanent": False})
    return rules


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def open_script(plan: EgressPlan) -> str:
    """Script PowerShell à exécuter en ADMINISTRATEUR par le propriétaire à l'ouverture de la fenêtre. Il ne contient aucune règle d'autorisation."""
    problems = plan.validate()
    if problems:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "invalid egress plan: " + "; ".join(problems))
    lines = ["# P0-D : règles de blocage de sortie (à lire AVANT exécution). Exécuter en administrateur. Générées par narrative_review.p0d.egress.",
             "$ErrorActionPreference = 'Stop'"]
    for r in _rules(plan):
        line = (f"New-NetFirewallRule -DisplayName {_ps(r['name'])} -Name {_ps(r['name'])} -Direction Outbound -Action Block -Enabled True -Profile Any "
                f"-Program {_ps(r['program'])} -RemoteAddress {_ps(','.join(r['remote']))} " + (f"-Protocol {r['protocol']} " if r['protocol'] != 'Any' else "") +
                (f"-RemotePort {_ps(','.join(r['port']))}" if r['port'] != ['Any'] else ""))
        lines.append(line.rstrip())
    names = ",".join(_ps(r["name"]) for r in _rules(plan) if not r["permanent"])
    lines += [f"$expire = {_ps(plan.window_end_iso)}",
              f"$cleanup = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -Command \"Remove-NetFirewallRule -Name ' + ({names} -join ',') + ' -ErrorAction SilentlyContinue\"')",
              f"Register-ScheduledTask -TaskName {_ps(RULE_PREFIX + '-' + plan.campaign_id + '-EXPIRE')} -Action $cleanup -Trigger (New-ScheduledTaskTrigger -Once -At ([datetime]$expire)) -Force | Out-Null",
              "Write-Output 'rules created: HARNESS blocked for all remote addresses; BROKER limited by complement-blocking to the provider IPs on TCP 443'"]
    return "\n".join(lines) + "\n"


def close_script(plan: EgressPlan) -> str:
    """Supprime les règles du COURTIER et la tâche d'expiration ; le blocage du harness reste en place (permanent)."""
    names = ",".join(_ps(r["name"]) for r in _rules(plan) if not r["permanent"])
    return ("$ErrorActionPreference = 'Stop'\n"
            f"Remove-NetFirewallRule -Name {names} -ErrorAction SilentlyContinue\n"
            f"Unregister-ScheduledTask -TaskName {_ps(RULE_PREFIX + '-' + plan.campaign_id + '-EXPIRE')} -Confirm:$false -ErrorAction SilentlyContinue\n")


def verify_script(plan: EgressPlan) -> str:
    """Lecture SEULE de l'état réel : toutes les règles dont le nom commence par le préfixe de la campagne, ET toute règle d'AUTORISATION visant l'un des deux programmes."""
    prefix = RULE_PREFIX + "-" + plan.campaign_id
    # Une seule requête en masse sur les filtres d'application (rapide), puis les filtres détaillés des SEULES règles retenues (les nôtres + celles qui visent nos programmes).
    return ("$ErrorActionPreference = 'Stop'\n"
            f"$apps = Get-NetFirewallApplicationFilter | Where-Object {{ $_.Program -ieq {_ps(plan.harness_program)} -or $_.Program -ieq {_ps(plan.broker_program)} }}\n"
            f"$rules = @(Get-NetFirewallRule -Name {_ps(prefix + '*')} -ErrorAction SilentlyContinue) + @($apps | Get-NetFirewallRule -ErrorAction SilentlyContinue)\n"
            "$mine = foreach ($r in ($rules | Sort-Object Name -Unique)) {\n"
            "  $a = $r | Get-NetFirewallApplicationFilter; $d = $r | Get-NetFirewallAddressFilter; $p = $r | Get-NetFirewallPortFilter\n"
            "  [pscustomobject]@{ Name = $r.Name; DisplayName = $r.DisplayName; Enabled = [string]$r.Enabled; Direction = [string]$r.Direction; Action = [string]$r.Action;\n"
            "    Program = $a.Program; RemoteAddress = @($d.RemoteAddress); Protocol = [string]$p.Protocol; RemotePort = @($p.RemotePort) } }\n"
            "ConvertTo-Json -InputObject @($mine) -Depth 4 -Compress\n")


def probe_command(plan: EgressPlan, program_role: str) -> str:
    """Sonde EXTERNE à CPython (à lancer par le propriétaire APRÈS application des règles) : tentative de connexion vers TEST-NET-1 depuis la copie dédiée du programme visé.
    Avec les règles, rien ne sort de la machine ; sans elles, le paquet part vers une adresse de documentation qu'aucun serveur ne peut atteindre."""
    exe = plan.harness_program if program_role == "harness" else plan.broker_program
    code = f"import socket; s=socket.socket(); s.settimeout(3); s.connect(('{PROBE_TARGET}', 80))"
    return f'& "{exe}" -I -c "{code}"; "exit code: $LASTEXITCODE (non zero attendu : bloqué ou injoignable)"'


# --- Analyse et attestation ---------------------------------------------------------------------------------------------------------

def _int_range(text: str):
    start, _, end = text.partition("-")
    s = ipaddress.ip_address(start.strip())
    return (int(s), int(ipaddress.ip_address(end.strip() if end else start.strip())), s.version)


def parse_firewall_state(json_text: str) -> list[dict]:
    """Normalise la sortie de `verify_script` (format réel de Get-NetFirewallRule). Une entrée mal formée est une erreur, jamais ignorée."""
    data = json.loads(json_text)
    data = [] if data in (None, "") else data
    if isinstance(data, dict):
        data = [data]
    rules = []
    for item in data:
        if not isinstance(item, dict) or not all(k in item for k in ("Name", "Enabled", "Direction", "Action", "Program", "RemoteAddress", "Protocol", "RemotePort")):
            raise ValueError("unexpected firewall rule shape")
        listify = lambda v: [str(x) for x in (v if isinstance(v, list) else [v])]  # noqa: E731
        rules.append({"name": item["Name"], "enabled": str(item["Enabled"]).lower() == "true", "direction": str(item["Direction"]), "action": str(item["Action"]),
                      "program": str(item["Program"] or ""), "remote": listify(item["RemoteAddress"]), "protocol": str(item["Protocol"]), "port": listify(item["RemotePort"])})
    return rules


@dataclass(frozen=True)
class Attestation:
    ok: bool
    problems: tuple[str, ...]
    sha256: str          # empreinte canonique du plan + des règles effectivement observées : à reporter dans `egress_attestation_sha256` de l'autorisation


def attest(plan: EgressPlan, state: list[dict]) -> Attestation:
    problems = [f"plan: {p}" for p in plan.validate()]
    p = RULE_PREFIX + "-" + plan.campaign_id
    mine = [r for r in state if r["name"].startswith(p)]
    by_name = {r["name"]: r for r in mine}
    wanted = {r["name"]: r for r in _rules(plan)}
    for name, want in wanted.items():
        got = by_name.get(name)
        if got is None:
            problems.append(f"missing rule {name}")
        elif not (got["enabled"] and got["direction"] == "Outbound" and got["action"] == want["action"] and got["program"].lower() == want["program"].lower()
                  and sorted(x.lower() for x in got["remote"]) == sorted(x.lower() for x in want["remote"])
                  and got["protocol"].lower() == want["protocol"].lower() and sorted(got["port"]) == sorted(want["port"])):
            problems.append(f"rule {name} is disabled or differs from the plan")
    problems += [f"unexpected rule {n}" for n in by_name if n not in wanted]
    for r in state:   # toute règle d'AUTORISATION active visant un des deux programmes ouvre un trou potentiel (hors profil par défaut)
        if r["enabled"] and r["action"] == "Allow" and r["direction"] == "Outbound" and r["program"].lower() in (plan.harness_program.lower(), plan.broker_program.lower()):
            problems.append(f"an enabled outbound Allow rule targets a campaign program: {r['name']}")
    # Couverture : blocages du courtier (hors règles UDP/ports) U IP du fournisseur = tout l'espace, sans chevauchement
    blocked = sorted(_int_range(x) for n, r in by_name.items() if "BROKER-BLOCK-OUTSIDE" in n and r["enabled"] for x in r["remote"] if x.lower() != "any")
    allowed = sorted(_int_range(ip) for ip in plan.provider_ips if re.fullmatch(r"[0-9a-fA-F:.]+", ip))
    for version, top in ((4, 2**32 - 1), (6, 2**128 - 1)):
        spans = sorted([s for s in blocked if s[2] == version] + [s for s in allowed if s[2] == version])
        cursor = 0
        for start, end, _v in spans:
            if start != cursor:
                problems.append(f"IPv{version} coverage gap or overlap at {ipaddress.ip_address(cursor) if cursor <= top else 'end'} vs {ipaddress.ip_address(start)}")
                break
            cursor = end + 1
        else:
            if cursor != top + 1:
                problems.append(f"IPv{version} coverage does not reach the end of the address space")
    canonical = json.dumps({"plan": plan.__dict__, "rules": sorted(({k: v for k, v in r.items()} for r in mine), key=lambda r: r["name"])}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return Attestation(not problems, tuple(problems), hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def live_attestation(plan: EgressPlan, run_powershell: Callable[[str], str]) -> Attestation:
    """Relit l'état RÉEL (`verify_script`, lecture seule) et l'atteste. `run_powershell` est INJECTÉ : les tests lui donnent un état simulé."""
    return attest(plan, parse_firewall_state(run_powershell(verify_script(plan))))
