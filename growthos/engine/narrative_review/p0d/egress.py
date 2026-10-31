"""Coupure de sortie réseau au niveau du SYSTÈME D'EXPLOITATION pour la future campagne : PROPOSITION + générateurs + vérificateur d'état. Rien n'est appliqué ici.

Principe : le courtier de transport est BLOQUÉ PAR DÉFAUT, y compris hors fenêtre. Aucune règle ne donne jamais un accès général ; une fenêtre ne fait que retirer UNE règle de verrou.
  - Le processus de CAMPAGNE (interpréteur « harness ») : bloqué en permanence pour toute adresse distante. La boucle locale n'est pas filtrée par le pare-feu Windows : il peut joindre
    un courtier local, et rien d'autre.
  - Le COURTIER (une COPIE dédiée de l'interpréteur, pour que les règles ne visent que lui) : comme un BLOCAGE l'emporte sur une AUTORISATION dans le pare-feu Windows, « seulement ces
    adresses » se code par le COMPLÉMENT. Règles PERMANENTES : `OUTSIDE` (UNE seule règle, plusieurs plages : tout l'espace d'adresses IPv4 et IPv6 SAUF les IP du fournisseur, donc atomique),
    blocage UDP, blocage des ports autres que 443 vers ces IP. Règle de VERROU `GATE` : blocage des IP du fournisseur elles-mêmes.
  - ÉTAT AU REPOS (par défaut) : toutes les règles, verrou compris => le courtier n'atteint RIEN. ÉTAT OUVERT (fenêtre) : le verrou est retiré => le courtier atteint les seules IP du
    fournisseur, TCP 443. Dans tous les cas, jamais d'accès général.
  - Ouverture = retrait du seul verrou, APRÈS vérification que toutes les règles permanentes existent et après enregistrement d'une tâche de refermeture. Fermeture, expiration, erreur
    partielle et redémarrage ne font que RAJOUTER le verrou (idempotent) : la direction sûre. Une tâche planifiée refait cet ajout à l'heure d'expiration ET au démarrage de la machine.
  - Propriété vérifiée par les tests : pour CHAQUE préfixe de chaque séquence (installation, ouverture, fermeture) et pour chaque règle supprimée, l'accès du courtier est inclus dans les
    IP du fournisseur ; au repos il est vide ; celui du harness est toujours vide.
Vérification indépendante de CPython : `verify_script` lit l'état RÉEL (lecture seule) ; `attest` le confronte au plan et à l'état attendu ; `reach` calcule ce que le courtier peut joindre ;
`probe_command` est une sonde externe (cible TEST-NET-1).

NON TESTÉ en conditions réelles : application des règles (droits d'administrateur requis), tâche planifiée, sonde, autres plateformes. Les tests couvrent la logique pure sur des états simulés au
format réel de `Get-NetFirewallRule`.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from .. import contract as c

RULE_PREFIX = "P0D"
PROBE_TARGET = "192.0.2.1"        # TEST-NET-1 (RFC 5737) : adresse de documentation, aucun serveur réel ne peut répondre
ALLOWED_PORT = 443
STATES = ("rest", "open")
_SPACE = {4: (0, 2**32 - 1), 6: (0, 2**128 - 1)}


@dataclass(frozen=True)
class EgressPlan:
    campaign_id: str
    harness_program: str      # chemin complet de l'interpréteur de la campagne
    broker_program: str       # chemin complet de la COPIE dédiée de l'interpréteur (courtier)
    provider_host: str        # information : le courtier se connecte aux IP ci-dessous, avec ce nom pour SNI
    provider_ips: tuple[str, ...]   # IP du fournisseur relevées par le propriétaire à l'ouverture de la fenêtre
    window_end_iso: str       # fin de fenêtre : la tâche planifiée rajoute le verrou

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
            if not addr.is_global or addr.is_multicast:
                problems.append(f"{ip} is not a public unicast address")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})", self.window_end_iso):
            problems.append("window_end_iso must be an ISO-8601 instant with a timezone")
        return problems


def _instant(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def check_consistency(plan: EgressPlan, auth_raw, *, now: datetime | None = None) -> list[str]:
    """Cohérence plan réseau <-> autorisation, à l'instant EFFECTIF de l'ouverture. Liste de problèmes (vide = cohérent). Tout doute doit laisser le courtier bloqué.

    Fin de fenêtre du plan = expiration de l'autorisation (au même instant, fuseaux compris), pas encore atteinte, et au plus 48 h devant nous ; même hôte ; même attestation approuvée."""
    now = now or datetime.now(timezone.utc)
    problems = [f"plan: {p}" for p in plan.validate()]
    end, expires = _instant(plan.window_end_iso), _instant(auth_raw.get("expires_at"))
    if end is None or expires is None:
        problems.append("window dates are not valid timezone-aware instants")
    else:
        if end != expires:
            problems.append("the network window end differs from the authorization expiry")
        if end <= now:
            problems.append("the network window is already expired at the moment of opening")
        if end - now > timedelta(hours=48):
            problems.append("the network window ends more than 48 h from now")
    if plan.provider_host != auth_raw.get("provider_host"):
        problems.append("the plan targets another provider host than the authorization")
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


def _name(plan: EgressPlan, suffix: str) -> str:
    return f"{RULE_PREFIX}-{plan.campaign_id}-{suffix}"


def permanent_rules(plan: EgressPlan) -> list[dict]:
    """Règles PERMANENTES, dans l'ordre d'installation : `OUTSIDE` d'abord (UNE règle atomique), le reste ensuite."""
    return [
        {"name": _name(plan, "BROKER-BLOCK-OUTSIDE"), "program": plan.broker_program, "action": "Block", "remote": [_range(r) for r in complement_ranges(plan.provider_ips)],
         "protocol": "Any", "port": ["Any"]},
        {"name": _name(plan, "BROKER-BLOCK-UDP"), "program": plan.broker_program, "action": "Block", "remote": ["Any"], "protocol": "UDP", "port": ["Any"]},
        {"name": _name(plan, "BROKER-BLOCK-OTHER-PORTS"), "program": plan.broker_program, "action": "Block", "remote": list(plan.provider_ips), "protocol": "TCP",
         "port": [f"1-{ALLOWED_PORT - 1}", f"{ALLOWED_PORT + 1}-65535"]},
        {"name": _name(plan, "HARNESS-BLOCK-ALL"), "program": plan.harness_program, "action": "Block", "remote": ["Any"], "protocol": "Any", "port": ["Any"]}]


def gate_rule(plan: EgressPlan) -> dict:
    """Verrou : bloque les IP du fournisseur pour le courtier. Présent au REPOS, retiré seulement pendant la fenêtre."""
    return {"name": _name(plan, "BROKER-BLOCK-GATE"), "program": plan.broker_program, "action": "Block", "remote": list(plan.provider_ips), "protocol": "Any", "port": ["Any"]}


def rules_for_state(plan: EgressPlan, state: str) -> list[dict]:
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}")
    return permanent_rules(plan) + ([gate_rule(plan)] if state == "rest" else [])


def _ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _create(r: dict) -> str:
    """Création IDEMPOTENTE d'une règle de blocage (ne fait rien si elle existe déjà et est activée ; la réactive sinon)."""
    args = (f"-DisplayName {_ps(r['name'])} -Name {_ps(r['name'])} -Direction Outbound -Action Block -Enabled True -Profile Any -Program {_ps(r['program'])} "
            f"-RemoteAddress {_ps(','.join(r['remote']))}" + (f" -Protocol {r['protocol']}" if r['protocol'] != 'Any' else "") +
            (f" -RemotePort {_ps(','.join(r['port']))}" if r['port'] != ['Any'] else ""))
    return (f"if (Get-NetFirewallRule -Name {_ps(r['name'])} -ErrorAction SilentlyContinue) {{ Enable-NetFirewallRule -Name {_ps(r['name'])} }} "
            f"else {{ New-NetFirewallRule {args} | Out-Null }}")


def _need_valid(plan: EgressPlan) -> None:
    problems = plan.validate()
    if problems:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "invalid egress plan: " + "; ".join(problems))


def install_script(plan: EgressPlan) -> str:
    """À exécuter UNE FOIS, en administrateur : crée l'état AU REPOS (courtier bloqué partout) et la tâche de refermeture. Ne crée aucune règle d'autorisation.
    Ordre : `OUTSIDE` (atomique) d'abord ; à chaque étape l'accès du courtier est inclus dans les IP du fournisseur (testé)."""
    _need_valid(plan)
    lines = ["# P0-D : installation de l'état AU REPOS (blocage par défaut). Exécuter en administrateur. Générée par narrative_review.p0d.egress.", "$ErrorActionPreference = 'Stop'"]
    lines += [_create(r) for r in permanent_rules(plan)] + [_create(gate_rule(plan)), _close_task(plan),
                                                           "Write-Output 'installed: REST state (broker blocked for every address, gate present)'"]
    return "\n".join(lines) + "\n"


def _close_task(plan: EgressPlan) -> str:
    """Tâche planifiée qui RAJOUTE le verrou à l'heure d'expiration ET au démarrage de la machine. Ne retire jamais aucune règle."""
    action = _create(gate_rule(plan)).replace('"', '`"')
    return (f"$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -Command \"' + {_ps(action)} + '\"')\n"
            f"$trg = @((New-ScheduledTaskTrigger -Once -At ([datetime]{_ps(plan.window_end_iso)})), (New-ScheduledTaskTrigger -AtStartup))\n"
            f"Register-ScheduledTask -TaskName {_ps(_name(plan, 'RECLOSE'))} -Action $act -Trigger $trg -RunLevel Highest -Force | Out-Null")


def open_script(plan: EgressPlan, *, now: datetime | None = None) -> str:
    """Ouvre la fenêtre : (1) vérifie que TOUTES les règles permanentes existent et sont actives (sinon `throw`, rien n'est retiré), (2) enregistre la tâche de refermeture,
    (3) retire LE SEUL verrou. En cas d'erreur à n'importe quelle étape, le verrou est encore là ou le courtier reste limité aux IP du fournisseur.
    Refuse (aucun script produit) si la fenêtre du plan est déjà expirée ; le script lui-même relit l'horloge de la machine, et vérifie profil, direction et action de chaque règle permanente."""
    _need_valid(plan)
    end, now = _instant(plan.window_end_iso), now or datetime.now(timezone.utc)
    if end is None or end <= now:
        raise c.ReviewError(c.BUDGET_EXHAUSTED, "the network window is already expired: the broker stays blocked")
    names = ",".join(_ps(r["name"]) for r in permanent_rules(plan))
    return ("$ErrorActionPreference = 'Stop'\n"
            f"if ([datetime]::UtcNow -ge [datetime]::Parse({_ps(end.astimezone(timezone.utc).isoformat())}).ToUniversalTime()) {{ throw 'the window is already expired: the gate stays' }}\n"
            f"foreach ($n in @({names})) {{ $r = Get-NetFirewallRule -Name $n -ErrorAction SilentlyContinue; if (-not $r -or [string]$r.Enabled -ne 'True' -or [string]$r.Direction -ne 'Outbound' "
            "-or [string]$r.Action -ne 'Block' -or [string]$r.Profile -ne 'Any') { throw \"permanent rule missing, disabled or not Block/Outbound/Any profile: $n\" } }\n"
            f"{_close_task(plan)}\n"
            f"Remove-NetFirewallRule -Name {_ps(gate_rule(plan)['name'])}\n"
            "Write-Output 'window OPEN: the broker can reach only the provider IPs on TCP 443; run close_script (or wait for the re-close task) to lock again'\n")


def close_script(plan: EgressPlan) -> str:
    """Fermeture : RAJOUTE le verrou (idempotent). Ne retire aucune règle."""
    _need_valid(plan)
    return "$ErrorActionPreference = 'Stop'\n" + _create(gate_rule(plan)) + "\nWrite-Output 'window CLOSED: gate present'\n"


def uninstall_script(plan: EgressPlan) -> str:
    """MAINTENANCE explicite (hors campagne) : supprime TOUT, y compris les blocages. Rend au courtier et au harness l'accès réseau par défaut de Windows : à ne jamais utiliser pendant une fenêtre."""
    names = ",".join(_ps(r["name"]) for r in rules_for_state(plan, "rest"))
    return ("# DANGER : rend au courtier et au harness l'accès réseau par défaut du système. Maintenance seulement.\n$ErrorActionPreference = 'Stop'\n"
            f"Remove-NetFirewallRule -Name {names} -ErrorAction SilentlyContinue\n"
            f"Unregister-ScheduledTask -TaskName {_ps(_name(plan, 'RECLOSE'))} -Confirm:$false -ErrorAction SilentlyContinue\n")


def verify_script(plan: EgressPlan) -> str:
    """Lecture SEULE de l'état réel : toutes les règles dont le nom commence par le préfixe de la campagne, ET toute règle visant l'un des deux programmes."""
    prefix = RULE_PREFIX + "-" + plan.campaign_id
    return ("$ErrorActionPreference = 'Stop'\n"
            f"$apps = Get-NetFirewallApplicationFilter | Where-Object {{ $_.Program -ieq {_ps(plan.harness_program)} -or $_.Program -ieq {_ps(plan.broker_program)} }}\n"
            f"$rules = @(Get-NetFirewallRule -Name {_ps(prefix + '*')} -ErrorAction SilentlyContinue) + @($apps | Get-NetFirewallRule -ErrorAction SilentlyContinue)\n"
            "$mine = foreach ($r in ($rules | Sort-Object Name -Unique)) {\n"
            "  $a = $r | Get-NetFirewallApplicationFilter; $d = $r | Get-NetFirewallAddressFilter; $p = $r | Get-NetFirewallPortFilter\n"
            "  [pscustomobject]@{ Name = $r.Name; DisplayName = $r.DisplayName; Enabled = [string]$r.Enabled; Direction = [string]$r.Direction; Action = [string]$r.Action; Profile = [string]$r.Profile;\n"
            "    Program = $a.Program; RemoteAddress = @($d.RemoteAddress); Protocol = [string]$p.Protocol; RemotePort = @($p.RemotePort) } }\n"
            "ConvertTo-Json -InputObject @($mine) -Depth 4 -Compress\n")


def probe_command(plan: EgressPlan, program_role: str) -> str:
    """Sonde EXTERNE à CPython (à lancer par le propriétaire APRÈS application des règles, à l'état AU REPOS) : tentative de connexion vers TEST-NET-1 depuis la copie dédiée du
    programme visé. Avec les règles, rien ne sort de la machine ; sans elles, le paquet part vers une adresse de documentation qu'aucun serveur ne peut atteindre."""
    exe = plan.harness_program if program_role == "harness" else plan.broker_program
    code = f"import socket; s=socket.socket(); s.settimeout(3); s.connect(('{PROBE_TARGET}', 80))"
    return f'& "{exe}" -I -c "{code}"; "exit code: $LASTEXITCODE (non zero attendu : bloqué ou injoignable)"'


# --- Analyse, portée et attestation -------------------------------------------------------------------------------------------------

def _int_range(text: str):
    text = text.strip()
    if "/" in text:
        net = ipaddress.ip_network(text, strict=False)
        return (int(net.network_address), int(net.broadcast_address), net.version)
    start, _, end = text.partition("-")
    s = ipaddress.ip_address(start.strip())
    return (int(s), int(ipaddress.ip_address(end.strip() if end else start.strip())), s.version)


def _ports(entries: list[str]) -> list[tuple[int, int]]:
    out = []
    for e in entries:
        if e.lower() == "any":
            return [(0, 65535)]
        lo, _, hi = e.partition("-")
        out.append((int(lo), int(hi or lo)))
    return out


def parse_firewall_state(json_text: str) -> list[dict]:
    """Normalise la sortie de `verify_script` (format réel de Get-NetFirewallRule). Une entrée mal formée est une erreur, jamais ignorée."""
    data = json.loads(json_text)
    data = [] if data in (None, "") else data
    if isinstance(data, dict):
        data = [data]
    rules = []
    for item in data:
        if not isinstance(item, dict) or not all(k in item for k in ("Name", "Enabled", "Direction", "Action", "Profile", "Program", "RemoteAddress", "Protocol", "RemotePort")):
            raise ValueError("unexpected firewall rule shape")
        listify = lambda v: [str(x) for x in (v if isinstance(v, list) else [v])]  # noqa: E731
        rules.append({"name": item["Name"], "enabled": str(item["Enabled"]).lower() == "true", "direction": str(item["Direction"]), "action": str(item["Action"]),
                      "profile": str(item["Profile"]),
                      "program": str(item["Program"] or ""), "remote": listify(item["RemoteAddress"]), "protocol": str(item["Protocol"]), "port": listify(item["RemotePort"])})
    return rules


def _as_state(rules: list[dict]) -> list[dict]:
    """Règles du plan (clés minuscules, `enabled` implicite) -> même forme que `parse_firewall_state`."""
    return [{**r, "enabled": r.get("enabled", True), "direction": r.get("direction", "Outbound"), "profile": r.get("profile", "Any")} for r in rules]


def reach(program: str, rules: list[dict], *, port: int | None = ALLOWED_PORT, protocol: str = "TCP") -> list[tuple[int, int, int]]:
    """Ce que `program` peut joindre en sortie sur `port`/`protocol` d'après ces règles : tout l'espace d'adresses MOINS l'union des règles de blocage actives qui s'appliquent.
    Hypothèse du pare-feu Windows : sortie autorisée par défaut, un blocage l'emporte sur une autorisation. Retourne des intervalles (début, fin, version IP)."""
    blocked: dict[int, list[tuple[int, int]]] = {4: [], 6: []}
    for r in _as_state(rules):
        if not (r["enabled"] and r["direction"] == "Outbound" and r["action"] == "Block" and r["program"].lower() == program.lower()):
            continue
        if r["profile"].lower() != "any":   # une règle limitée à certains profils Windows (Domain/Private/Public) ne bloque pas les autres : elle ne compte pas comme blocage
            continue
        if r["protocol"].lower() not in ("any", protocol.lower()):
            continue
        if port is not None and not any(lo <= port <= hi for lo, hi in _ports(r["port"])):
            continue
        for remote in r["remote"]:
            if remote.lower() == "any":
                blocked[4].append(_SPACE[4])
                blocked[6].append(_SPACE[6])
            else:
                s, e, v = _int_range(remote)
                blocked[v].append((s, e))
    out = []
    for version, (lo, hi) in _SPACE.items():
        cursor = lo
        for s, e in sorted(blocked[version]):
            if s > cursor:
                out.append((cursor, s - 1, version))
            cursor = max(cursor, e + 1)
        if cursor <= hi:
            out.append((cursor, hi, version))
    return out


def provider_span(plan: EgressPlan) -> list[tuple[int, int, int]]:
    return sorted((int(ipaddress.ip_address(ip)),) * 2 + (ipaddress.ip_address(ip).version,) for ip in plan.provider_ips)


def reach_within_provider(plan: EgressPlan, rules: list[dict]) -> bool:
    """Vrai si l'accès du courtier est INCLUS dans les IP du fournisseur (le seul état acceptable, y compris pendant une transition)."""
    allowed = {(s, v) for s, _e, v in provider_span(plan)}
    for s, e, v in reach(plan.broker_program, rules):
        if e - s + 1 > len(allowed) or any((a, v) not in allowed for a in range(s, e + 1)):   # un intervalle plus large que la liste des IP ne peut pas en être un sous-ensemble
            return False
    return True


@dataclass(frozen=True)
class Attestation:
    ok: bool
    problems: tuple[str, ...]
    sha256: str          # empreinte canonique du plan, de l'état attendu et des règles observées : à reporter dans `egress_attestation_sha256` de l'autorisation (état « rest »)
    expected_state: str


def attest(plan: EgressPlan, state: list[dict], *, expect: str = "rest") -> Attestation:
    """Confronte l'état observé du pare-feu au plan pour l'état attendu (`rest` : verrou présent, courtier bloqué partout ; `open` : verrou retiré, courtier limité aux IP du fournisseur)."""
    problems = [f"plan: {p}" for p in plan.validate()]
    prefix = RULE_PREFIX + "-" + plan.campaign_id
    mine = [r for r in state if r["name"].startswith(prefix)]
    by_name = {r["name"]: r for r in mine}
    wanted = {r["name"]: r for r in rules_for_state(plan, expect)}
    for name, want in wanted.items():
        got = by_name.get(name)
        if got is None:
            problems.append(f"missing rule {name}")
        elif not (got["enabled"] and got["direction"] == "Outbound" and got["action"] == want["action"] and got["profile"].lower() == "any"
                  and got["program"].lower() == want["program"].lower()
                  and sorted(x.lower() for x in got["remote"]) == sorted(x.lower() for x in want["remote"])
                  and got["protocol"].lower() == want["protocol"].lower() and sorted(got["port"]) == sorted(want["port"])):
            problems.append(f"rule {name} is disabled or differs from the plan")
    problems += [f"unexpected rule {n}" for n in by_name if n not in wanted]
    for r in state:   # toute règle d'AUTORISATION active visant un des deux programmes ouvre un trou potentiel
        if r["enabled"] and r["action"] == "Allow" and r["direction"] == "Outbound" and r["program"].lower() in (plan.harness_program.lower(), plan.broker_program.lower()):
            problems.append(f"an enabled outbound Allow rule targets a campaign program: {r['name']}")
    # Portée RÉELLE calculée sur l'état observé : le harness ne joint rien ; le courtier ne joint rien (repos) ou seulement les IP du fournisseur (ouvert)
    if reach(plan.harness_program, state, port=None, protocol="Any"):
        problems.append("the harness program is not blocked for every remote address (on every Windows profile)")
    broker = reach(plan.broker_program, state)
    if expect == "rest" and broker:
        problems.append("at rest the broker can still reach some addresses on TCP 443")
    if expect == "open" and not reach_within_provider(plan, state):
        problems.append("while open the broker can reach more than the provider IPs on TCP 443")
    if reach(plan.broker_program, state, port=None, protocol="UDP"):
        problems.append("the broker can use UDP")
    canonical = json.dumps({"plan": plan.__dict__, "expected": expect, "rules": sorted(({k: v for k, v in r.items()} for r in mine), key=lambda r: r["name"])},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return Attestation(not problems, tuple(problems), hashlib.sha256(canonical.encode("utf-8")).hexdigest(), expect)


def live_attestation(plan: EgressPlan, run_powershell: Callable[[str], str], *, expect: str = "rest") -> Attestation:
    """Relit l'état RÉEL (`verify_script`, lecture seule) et l'atteste. `run_powershell` est INJECTÉ : les tests lui donnent un état simulé."""
    return attest(plan, parse_firewall_state(run_powershell(verify_script(plan))), expect=expect)


# --- Séquences d'opérations (pour prouver qu'aucune étape intermédiaire n'élargit l'accès) -----------------------------------------------

def install_steps(plan: EgressPlan) -> list[tuple[str, dict]]:
    return [("create", r) for r in permanent_rules(plan)] + [("create", gate_rule(plan))]


def open_steps(plan: EgressPlan) -> list[tuple[str, dict]]:
    return [("remove", gate_rule(plan))]            # la vérification des règles permanentes et l'enregistrement de la tâche n'ajoutent ni ne retirent aucune règle


def close_steps(plan: EgressPlan) -> list[tuple[str, dict]]:
    return [("create", gate_rule(plan))]


def apply_step(rules: list[dict], step: tuple[str, dict]) -> list[dict]:
    op, rule = step
    if op == "create":
        return [r for r in rules if r["name"] != rule["name"]] + [rule]
    return [r for r in rules if r["name"] != rule["name"]]
