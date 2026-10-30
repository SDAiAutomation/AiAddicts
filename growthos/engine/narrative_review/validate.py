"""Validation déterministe de la réponse du critique. Échec FERMÉ : une seule erreur invalide la réponse entière.

Le serveur vérifie références, ancrages, couverture et calculs. Il NE prétend PAS démontrer l'implication sémantique d'un
extrait de source, ni l'exhaustivité du registre d'affirmations (voir NARRATIVE_P0_RISK_REGISTER R01).
"""
from __future__ import annotations

import ast
import math
import re

from . import contract as c

_RESPONSE_KEYS = {"schema_version", "coverage", "claims", "findings"}
_COVERAGE_KEYS = {"dimension", "status", "reason", "inspected_unit_ids"}
_CLAIM_KEYS = {"claim_id", "anchor", "assessment", "source_evidence", "reason", "calculation"}
_FINDING_KEYS = {"finding_id", "code", "dimension", "severity", "assessment", "anchors", "source_evidence",
                 "inspected_unit_ids", "reason", "suggestion", "repair_scope"}
_CALC_KEYS = {"expression", "operands", "unit", "expected_result", "stated_result"}
_ANCHOR_KEYS = {"unit_id", "quote", "occurrence"}
_SOURCE_ANCHOR_KEYS = {"source_id", "quote", "occurrence"}


def _bad(msg: str, code: str = c.INVALID_RESPONSE):
    raise c.ReviewError(code, msg)


def _exact_keys(obj, keys: set, where: str) -> None:
    if not isinstance(obj, dict):
        _bad(f"{where} must be an object")
    extra, missing = set(obj) - keys, keys - set(obj)
    if extra or missing:
        _bad(f"{where}: unexpected keys {sorted(extra)} / missing keys {sorted(missing)}")


def _text(value, where: str, limit: int = c.TEXT_MAX) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        _bad(f"{where} must be a text of 1..{limit} characters")
    return value


def _enum(value, allowed, where: str):
    if not isinstance(value, str) or value not in allowed:
        _bad(f"{where}: {value!r} is not one of {list(allowed)}")
    return value


def locate(text: str, quote: str, occurrence: int) -> int:
    """n-ième occurrence (index 0) d'une sous-chaîne exacte, sensible à la casse, de gauche à droite, sans chevauchement."""
    pos = -1
    for _ in range(occurrence + 1):
        pos = text.find(quote, pos + 1 if pos < 0 else pos + len(quote))
        if pos < 0:
            return -1
    return pos


def _anchor_fields(a, keys: set, where: str):
    _exact_keys(a, keys, where)
    quote, occ = a["quote"], a["occurrence"]
    if not isinstance(quote, str) or not 1 <= len(quote) <= c.QUOTE_MAX:
        _bad(f"{where}.quote must be 1..{c.QUOTE_MAX} characters", c.INVALID_ANCHOR)
    if not isinstance(occ, int) or isinstance(occ, bool) or occ < 0:
        _bad(f"{where}.occurrence must be an integer >= 0", c.INVALID_ANCHOR)
    return quote, occ


def check_text_anchor(a, units: dict, where: str) -> str:
    quote, occ = _anchor_fields(a, _ANCHOR_KEYS, where)
    unit = units.get(a["unit_id"]) if isinstance(a["unit_id"], str) else None
    if unit is None:
        _bad(f"{where}: unknown unit_id {a['unit_id']!r}", c.INVALID_ANCHOR)
    if locate(unit["text"], quote, occ) < 0:
        _bad(f"{where}: quote not found in {a['unit_id']} at occurrence {occ}", c.INVALID_ANCHOR)
    return a["unit_id"]


def check_source_anchor(a, sources: dict, where: str) -> None:
    quote, occ = _anchor_fields(a, _SOURCE_ANCHOR_KEYS, where)
    src = sources.get(a["source_id"]) if isinstance(a["source_id"], str) else None
    if src is None:
        _bad(f"{where}: source {a['source_id']!r} was not provided", c.INVALID_ANCHOR)
    if locate(src["content"], quote, occ) < 0:
        _bad(f"{where}: quote not found in source {a['source_id']}", c.INVALID_ANCHOR)


_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b}


def safe_eval(expression: str, operands: dict) -> float:
    """Calculateur à opérations autorisées (+ - * / et parenthèses, opérandes NOMMÉS uniquement). Jamais `eval`."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        _bad("calculation.expression is not a valid arithmetic expression")

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            right = walk(node.right)
            left = walk(node.left)
            if isinstance(node.op, ast.Div) and right == 0:
                _bad("calculation divides by zero")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Name) and node.id in operands:
            return operands[node.id]
        _bad(f"calculation uses a forbidden construct ({type(node).__name__})")
    return walk(tree)


def _number(v, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        _bad(f"{where} must be a finite number")
    return float(v)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _number_in_quote(value: float, quote: str) -> bool:
    return any(math.isclose(value, float(m.replace(",", ".")), rel_tol=1e-9, abs_tol=1e-9) for m in _NUMBER.findall(quote))


def _check_calculation(calc, units: dict, where: str, claim_quote: str) -> bool:
    """Retourne True si `expected_result == stated_result`. Le résultat attendu est RECALCULÉ, jamais cru."""
    _exact_keys(calc, _CALC_KEYS, where)
    _text(calc["expression"], f"{where}.expression", 200)
    _text(calc["unit"], f"{where}.unit", 40)
    if not isinstance(calc["operands"], dict) or not calc["operands"]:
        _bad(f"{where}.operands must be a non-empty object")
    values = {}
    for name, op in calc["operands"].items():
        _exact_keys(op, {"value", "anchor"}, f"{where}.operands.{name}")
        values[name] = _number(op["value"], f"{where}.operands.{name}.value")
        check_text_anchor(op["anchor"], units, f"{where}.operands.{name}.anchor")
        # shortcut: seuls les chiffres sont reconnus ; un nombre écrit en toutes lettres ne peut pas servir d'opérande (réponse refusée,
        # donc `review`). À étendre avec un analyseur de nombres par langue si les cas réels l'exigent.
        if not _number_in_quote(values[name], op["anchor"]["quote"]):
            _bad(f"{where}.operands.{name}: the value {values[name]} does not appear in its anchored quote", c.INVALID_ANCHOR)
    computed = safe_eval(calc["expression"], values)
    expected, stated = _number(calc["expected_result"], f"{where}.expected_result"), _number(calc["stated_result"], f"{where}.stated_result")
    if not math.isclose(computed, expected, rel_tol=1e-9, abs_tol=1e-9):
        _bad(f"{where}: expected_result {expected} does not match the recomputed value {computed}")
    if not _number_in_quote(stated, claim_quote):
        _bad(f"{where}.stated_result {stated} does not appear in the claim anchor", c.INVALID_ANCHOR)
    return math.isclose(expected, stated, rel_tol=1e-9, abs_tol=1e-9)


def _unit_ids(value, units: dict, where: str) -> list:
    if not isinstance(value, list) or any(not isinstance(u, str) or u not in units for u in value):
        _bad(f"{where} must list known unit ids", c.INVALID_ANCHOR)
    return value


def validate_response(raw: dict, snapshot: dict) -> dict:
    """Retourne la réponse validée (même objet) ou lève `ReviewError`. Ne supprime JAMAIS un défaut pour réussir."""
    units = {u["unit_id"]: u for u in snapshot["units"]}
    spoken = {u["unit_id"] for u in snapshot["units"] if u["channel"] == "spoken"}
    sources = {s["source_id"]: s for s in snapshot["sources"]}
    required = list(snapshot["required_dimensions"])
    _exact_keys(raw, _RESPONSE_KEYS, "response")
    if raw["schema_version"] != c.SCHEMA_VERSION:
        _bad(f"schema_version must be {c.SCHEMA_VERSION}")
    for key in ("coverage", "claims", "findings"):
        if not isinstance(raw[key], list):
            _bad(f"{key} must be a list")

    seen, status_by_dim = [], {}
    for i, cov in enumerate(raw["coverage"]):
        where = f"coverage[{i}]"
        _exact_keys(cov, _COVERAGE_KEYS, where)
        _enum(cov["dimension"], c.DIMENSIONS, f"{where}.dimension")
        _enum(cov["status"], c.COVERAGE_STATUSES, f"{where}.status")
        _text(cov["reason"], f"{where}.reason")
        inspected = _unit_ids(cov["inspected_unit_ids"], units, f"{where}.inspected_unit_ids")
        if cov["status"] in ("evaluated", "partial") and not inspected:
            _bad(f"{where}: an evaluated or partial dimension must list the units it inspected")
        if cov["status"] == "evaluated" and not spoken <= set(inspected):
            # un jugement sur le texte entier ne peut pas être « evaluated » après lecture d'une seule unité : déclarer `partial`
            _bad(f"{where}: an evaluated dimension must inspect every spoken unit (declare it partial otherwise)", c.INCOMPLETE_COVERAGE)
        if cov["status"] == "not_applicable" and not (
                cov["dimension"] == "truth" and snapshot["truth_mode"] == "fiction" and snapshot["illustration_mode"] != "hypothetical"):
            # shortcut: seule `truth` peut être non applicable (fiction explicite, hors simulation) ; les autres dimensions
            # obligatoires ne peuvent pas disparaître. À assouplir si le corpus de relecture humaine montre des cas légitimes.
            _bad(f"{where}: {cov['dimension']} cannot be not_applicable in this mode")
        seen.append(cov["dimension"])
        status_by_dim[cov["dimension"]] = cov["status"]
    if sorted(seen) != sorted(required):
        _bad(f"coverage must contain exactly one entry per requested dimension {required}", c.INCOMPLETE_COVERAGE)

    if len(raw["claims"]) > c.MAX_CLAIMS:
        _bad("too many claims", c.INPUT_TOO_LARGE)
    claim_ids, calc_contradictions, factual_claims = set(), 0, 0
    for i, cl in enumerate(raw["claims"]):
        where = f"claims[{i}]"
        _exact_keys(cl, _CLAIM_KEYS, where)
        _text(cl["claim_id"], f"{where}.claim_id", 80)
        if cl["claim_id"] in claim_ids:
            _bad(f"{where}: duplicate claim_id")
        claim_ids.add(cl["claim_id"])
        check_text_anchor(cl["anchor"], units, f"{where}.anchor")
        _enum(cl["assessment"], c.CLAIM_ASSESSMENTS, f"{where}.assessment")
        _text(cl["reason"], f"{where}.reason")
        if not isinstance(cl["source_evidence"], list):
            _bad(f"{where}.source_evidence must be a list")
        for j, ev in enumerate(cl["source_evidence"]):
            check_source_anchor(ev, sources, f"{where}.source_evidence[{j}]")
        calc_ok = None
        if cl["calculation"] is not None:
            calc_ok = _check_calculation(cl["calculation"], units, f"{where}.calculation", cl["anchor"]["quote"])
        if cl["assessment"] in ("supported", "contradicted") and not cl["source_evidence"] and cl["calculation"] is None:
            _bad(f"{where}: {cl['assessment']} needs source evidence or a verifiable calculation")
        if calc_ok is True and cl["assessment"] == "contradicted" and not cl["source_evidence"]:
            _bad(f"{where}: the calculation matches the stated result, it cannot support 'contradicted'")
        if calc_ok is False and cl["assessment"] != "contradicted":
            # un calcul faux ne peut être étiqueté ni supported, ni not_factual, ni unverified : sinon il passerait sans défaut
            _bad(f"{where}: the calculation contradicts the stated result, the claim must be 'contradicted'")
        if calc_ok is False:
            calc_contradictions += 1
        if cl["assessment"] != "not_factual":
            factual_claims += 1
    if status_by_dim.get("truth") == "not_applicable" and factual_claims:
        _bad("truth cannot be not_applicable while factual claims are registered")

    if len(raw["findings"]) > c.MAX_FINDINGS:
        _bad("too many findings", c.INPUT_TOO_LARGE)
    finding_ids = set()
    for i, f in enumerate(raw["findings"]):
        where = f"findings[{i}]"
        _exact_keys(f, _FINDING_KEYS, where)
        _text(f["finding_id"], f"{where}.finding_id", 80)
        if f["finding_id"] in finding_ids:
            _bad(f"{where}: duplicate finding_id")
        finding_ids.add(f["finding_id"])
        code = _enum(f["code"], c.CODES, f"{where}.code")
        dimension, severities = c.CODES[code]
        if f["dimension"] != dimension:
            _bad(f"{where}: code {code} belongs to dimension {dimension}, not {f['dimension']!r}")
        if status_by_dim.get(dimension) in ("not_applicable", "unavailable"):
            _bad(f"{where}: a finding cannot target dimension {dimension}, declared {status_by_dim[dimension]}", c.INCOMPLETE_COVERAGE)
        if _enum(f["severity"], c.SEVERITIES, f"{where}.severity") not in severities:
            _bad(f"{where}: severity {f['severity']!r} is not allowed for {code}")
        _enum(f["assessment"], c.ASSESSMENTS, f"{where}.assessment")
        _enum(f["repair_scope"], c.REPAIR_SCOPES, f"{where}.repair_scope")
        _text(f["reason"], f"{where}.reason")
        _text(f["suggestion"], f"{where}.suggestion")
        anchors = f["anchors"]
        if not isinstance(anchors, list) or not 1 <= len(anchors) <= c.MAX_ANCHORS:
            _bad(f"{where}.anchors must hold 1..{c.MAX_ANCHORS} anchors", c.INVALID_ANCHOR)
        for j, a in enumerate(anchors):
            check_text_anchor(a, units, f"{where}.anchors[{j}]")
        if not isinstance(f["source_evidence"], list):
            _bad(f"{where}.source_evidence must be a list")
        for j, ev in enumerate(f["source_evidence"]):
            check_source_anchor(ev, sources, f"{where}.source_evidence[{j}]")
        inspected = _unit_ids(f["inspected_unit_ids"], units, f"{where}.inspected_unit_ids")
        if code in c.TWO_ANCHOR_CODES and len(anchors) < 2:
            _bad(f"{where}: {code} needs at least two anchors", c.INVALID_ANCHOR)
        if code in c.ABSENCE_CODES and not spoken <= set(inspected):
            _bad(f"{where}: an alleged absence must list every spoken unit it examined", c.INCOMPLETE_COVERAGE)
        if code == "FACT_UNVERIFIED" and (f["assessment"], f["severity"], f["repair_scope"]) != ("uncertain", "blocker", "needs_sources"):
            _bad(f"{where}: FACT_UNVERIFIED must be uncertain / blocker / needs_sources")
        if code == "FACT_CONTRADICTED" and not f["source_evidence"] and not calc_contradictions:
            _bad(f"{where}: FACT_CONTRADICTED needs source evidence or a verified contradicting calculation")
        if code == "FABRICATED_ATTRIBUTION" and not f["source_evidence"]:
            _bad(f"{where}: without documentary proof, report FACT_UNVERIFIED instead of FABRICATED_ATTRIBUTION")
    return raw
