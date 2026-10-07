"""Plan structuré d'une scène `equation_steps` : étapes, opérations, événements, timeline.

Une SEULE source de vérité pour le calcul, la narration et l'animation. Le plan est calculé en
Python à partir des étapes validées (`math_validation`) et des mots RÉELS de la voix
(`audio/block-NN.words.json`) ; le rendu Manim ne fait que le jouer. Il ne reconstruit aucune
sémantique à partir du LaTeX.

Contrat d'une étape (script) — tout est optionnel sauf `equation` :
    equation       "3x + 6 = 18"        texte mathématique (validé, exact)
    explanation    "−6 des deux côtés"   annotation courte AFFICHÉE près de l'opération
    spoken         "on retire six"       repère vocal : l'opération est nommée à ce moment
    sidesSpoken    "des deux côtés"      repère vocal : « aux deux membres » (sinon cherché après `spoken`)
    resultSpoken   "trois x égale douze" repère vocal : le résultat apparaît (sinon : mot suivant)
La structure dérivée (`plan["steps"][i]`) ajoute : `operation` (kind/tex/display), `left`/`right`
(LaTeX d'affichage), `intermediate` (l'équation avec l'opération écrite des deux côtés),
`cancel` (terme annulé de chaque côté), `events` (secondes dans le bloc), `validation`.
Le texte destiné à la voix reste celui du bloc (`text`) ; ce module n'écrit jamais de narration.

Aucun repère trouvé pour une étape → rythme de repli régulier, signalé (`timing: "fallback"`).
Les durées de `RHYTHM` sont des valeurs à tester, pas des normes ; surchargeables par la scène
(`rhythm`) ou par la variable d'environnement `MATH_RHYTHM_JSON`.
"""
from __future__ import annotations

import json
import os
import re
from fractions import Fraction

from . import math_validation as mv
from .sync import LEAD_SECONDS, _tokens

PLAN_VERSION = 1

RHYTHM: dict[str, float] = {
    "op_in": 0.4,            # apparition de l'opération (étiquette « −6 »)
    "op_to_sides_min": 0.35, # entre « on retire six » et « des deux côtés »
    "sides_move": 0.55,       # l'opération est écrite des deux côtés
    "sides_to_apply_min": 0.55,
    "apply_anim": 0.9,       # annulation + simplification
    "gap_min": 0.3,          # entre la fin d'une étape et l'opération suivante
    "apply_lead": 0.3,       # le résultat commence un peu avant d'être prononcé
    "result_hold": 1.4,      # temps de lecture du résultat final
    "verify_anim": 1.4,
    "verify_gap": 0.25,
}

_SIDE_WORDS = {"côtés", "côté", "cotes", "cote", "membres", "membre", "sides", "side", "lados", "lado",
               "seiten", "seite", "lati", "lato"}
_BOTH_WORDS = {"deux", "both", "ambos", "beiden", "entrambi"}
_VERIFY_WORDS = {"vérification", "verification", "vérifions", "vérifie", "check", "verify", "comprobación", "prüfung"}


def rhythm_for(scene: dict | None = None) -> dict[str, float]:
    values = dict(RHYTHM)
    for source in (os.environ.get("MATH_RHYTHM_JSON", ""), (scene or {}).get("rhythm")):
        try:
            extra = json.loads(source) if isinstance(source, str) and source.strip() else source
        except ValueError:
            extra = None
        if isinstance(extra, dict):
            for key, value in extra.items():
                if key in values and isinstance(value, (int, float)) and 0 <= value <= 10:
                    values[key] = float(value)
    return values


# ---------------------------------------------------------------------------
# Texte mathématique → LaTeX d'affichage
# ---------------------------------------------------------------------------

def split_equation(equation: str) -> tuple[str, str] | None:
    """(gauche, droite) pour une égalité unique ; None pour « x = 2 ou x = 3 » et autres."""
    if equation.count("=") != 1 or re.search(r"\bou\b", equation, flags=re.I):
        return None
    left, right = (part.strip() for part in equation.split("="))
    return (left, right) if left and right else None


_FRAC = re.compile(r"(\([^()]*\)|[0-9][0-9.,]*|x)\s*[/⁄]\s*(\([^()]*\)|[0-9][0-9.,]*|x)")


def side_tex(side: str) -> str:
    """Un membre prêt pour LaTeX : signes, produits, divisions simples en fractions."""
    s = str(side or "").strip().replace("−", "-").replace("×", r"\times").replace("÷", r"\div")
    s = s.replace("²", "^2").replace("·", r"\cdot")
    s = re.sub(r"(?<=\d)\*(?=x)", "", s).replace("*", r"\cdot")

    def fraction(match: re.Match) -> str:
        numerator, denominator = match[1], match[2]
        strip = lambda part: part[1:-1] if part.startswith("(") and part.endswith(")") else part  # noqa: E731
        return rf"\frac{{{strip(numerator)}}}{{{strip(denominator)}}}"

    s = _FRAC.sub(fraction, s)
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)
    return re.sub(r"\s+", " ", s).strip()


def split_terms(tex: str) -> list[tuple[str, str]]:
    """Termes de plus haut niveau [(signe, corps)], hors parenthèses/accolades."""
    terms, depth, current, sign = [], 0, "", "+"
    for char in tex.strip():
        if char in "({":
            depth += 1
        elif char in ")}":
            depth -= 1
        if char in "+-" and depth == 0 and current.strip():
            terms.append((sign, current.strip()))
            sign, current = char, ""
        elif char in "+-" and depth == 0 and not current.strip():
            sign = "-" if (char == "-") != (sign == "-") else "+"
        else:
            current += char
    if current.strip():
        terms.append((sign, current.strip()))
    return terms


def term_parts(tex: str) -> list[str]:
    """Le membre découpé en morceaux LaTeX par terme (« 3x + 6 » → ["3x", "+ 6"]) : chaque morceau
    devient un objet visuel distinct, donc un terme annulé est désigné par son rang, pas deviné."""
    terms = split_terms(tex)
    if not terms:
        return [tex]
    # « {} » devant « + » / « - » : sans lui, LaTeX voit un signe unaire en début de morceau et
    # supprime l'espace à gauche (« 2x+ 6 » au lieu de « 2x + 6 »).
    return [(("-" if sign == "-" else "") if i == 0 else ("{}- " if sign == "-" else "{}+ ")) + body
            for i, (sign, body) in enumerate(terms)]


def _with_operation(side: str, operation: dict) -> str:
    """Le membre avec l'opération écrite dessus (« 3x + 6 » + « −6 » → « 3x + 6 - 6 »)."""
    kind = operation["kind"]
    if kind == "add":
        return f"{side} {operation['tex']}"
    amount = Fraction(operation["amount"])
    if kind == "div":
        return rf"\frac{{{side}}}{{{amount.numerator if amount.denominator == 1 else amount}}}"
    shown = mv._fraction_tex(amount)
    shown = f"({shown})" if amount < 0 else shown
    multi = len(split_terms(side)) > 1
    return rf"{shown} \left( {side} \right)" if multi else rf"{shown} \cdot {side}"


def _cancel_index(side: str, operation: dict) -> int | None:
    """Terme du membre annulé par l'opération (3x + 6, −6 → le « + 6 »), sinon None."""
    if operation.get("kind") != "add":
        return None
    amount = Fraction(operation["amount"])
    body = ("" if amount == 1 and operation["withX"] else mv._fraction_tex(amount)) + ("x" if operation["withX"] else "")
    opposite = "-" if operation["sign"] == "+" else "+"
    for index, (sign, text) in enumerate(split_terms(side)):
        if sign == opposite and text.replace(" ", "") == body:
            return index
    return None


# ---------------------------------------------------------------------------
# Repères vocaux
# ---------------------------------------------------------------------------

def _spoken_tokens(words: list[dict] | None) -> list[tuple[str, float, float, bool]]:
    """(mot utile, début, fin, vient-après-un-« : »). Le deux-points annonce le résultat prononcé."""
    out = []
    after_colon = False
    for word in words or []:
        raw = str(word.get("text") or "")
        start = float(word.get("start") or 0.0)
        end = float(word.get("end") or start)
        for token in _tokens(raw):
            out.append((token, start, end, after_colon))
            after_colon = False
        if raw.strip().endswith(":"):
            after_colon = True
    return out


def _find_phrase(spoken: list, phrase: object, cursor: int = 0) -> tuple[int, int] | None:
    wanted = _tokens(str(phrase or ""))
    if not wanted:
        return None
    for i in range(max(cursor, 0), len(spoken) - len(wanted) + 1):
        if [item[0] for item in spoken[i:i + len(wanted)]] == wanted:
            return i, i + len(wanted)
    return None


def _anchors_for_step(spoken: list, step: dict, cursor: int, next_step: dict | None = None) -> dict | None:
    """Instants (s) du nom de l'opération, de « aux deux membres » et du résultat, ou None.

    Les recherches s'arrêtent avant l'opération de l'étape suivante : « aux deux côtés » de la
    suivante ne doit jamais être pris pour celui-ci."""
    op = _find_phrase(spoken, step.get("spoken"), cursor)
    if op is None:
        return None
    following = _find_phrase(spoken, next_step.get("spoken"), op[1]) if next_step else None
    limit = following[0] if following else len(spoken)
    anchors: dict = {"op": spoken[op[0]][1], "end": op[1]}
    sides_end = op[1]
    explicit = _find_phrase(spoken, step.get("sidesSpoken"), op[0]) if step.get("sidesSpoken") else None
    if explicit is not None:
        anchors["sides"], sides_end = spoken[explicit[0]][1], explicit[1]
    else:
        for j in range(op[1], min(op[1] + 8, limit)):
            if spoken[j][0] in _SIDE_WORDS:
                first = j - 1 if j - 1 >= op[1] and spoken[j - 1][0] in _BOTH_WORDS else j
                anchors["sides"], sides_end = spoken[first][1], j + 1
                break
    result = _find_phrase(spoken, step.get("resultSpoken"), sides_end) if step.get("resultSpoken") else None
    if result is not None:
        anchors["result"], anchors["end"] = spoken[result[0]][1], result[1]
    elif sides_end < limit:
        # Après « des deux côtés », l'opération peut avoir un complément (« par trois ») : le
        # résultat commence au mot qui suit le « : » de la voix, sinon au mot suivant.
        target = next((j for j in range(sides_end, min(sides_end + 6, limit)) if spoken[j][3]), sides_end)
        anchors["result"], anchors["end"] = spoken[target][1], target + 1
    else:
        anchors["end"] = sides_end
    return anchors


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def _annotation(step: dict, operation: dict | None, language: str) -> str:
    text = str(step.get("explanation") or "").strip()
    if text or not operation or operation.get("kind") in ("rewrite", "unknown"):
        return text
    return f"{operation['display']} {'des deux côtés' if language == 'fr' else 'on both sides'}"


def build_plan(scene: dict, words: list[dict] | None, duration: float, language: str = "fr") -> dict:
    """Plan complet de la scène. Pur : mêmes entrées, même plan ; ne lève pas pour une scène valide."""
    rhythm = rhythm_for(scene)
    steps_in = [s for s in (scene.get("steps") or [])[:4] if isinstance(s, dict) and isinstance(s.get("equation"), str)]
    check = mv.verify_steps(steps_in) if len(steps_in) >= 2 else {"status": "unverified", "reason": "étapes insuffisantes"}
    warnings: list[str] = []
    plan_steps: list[dict] = []
    for index, step in enumerate(steps_in):
        equation = step["equation"].strip()
        halves = split_equation(equation)
        operation = None
        if index > 0 and halves and split_equation(steps_in[index - 1]["equation"]):
            operation = mv.describe_operation(steps_in[index - 1]["equation"], equation)
        entry: dict = {
            "id": f"s{index}", "index": index, "equation": equation,
            "left": side_tex(halves[0]) if halves else None, "right": side_tex(halves[1]) if halves else None,
            "line": None if halves else side_tex(re.sub(r"\bou\b", r"\\text{ ou }", equation, flags=re.I)),
            "operation": operation,
            "narration": {k: step[k] for k in ("spoken", "sidesSpoken", "resultSpoken") if isinstance(step.get(k), str)},
            "annotation": _annotation(step, operation, language),
            "validation": {"status": check["status"], **({"reason": check["reason"]} if check.get("reason") else {}),
                           "excludedValues": check.get("excludedValues", [])},
        }
        if index > 0 and halves and operation and operation["kind"] in ("add", "mul", "div") and plan_steps[-1]["left"]:
            previous = plan_steps[-1]
            entry["intermediate"] = {"left": _with_operation(previous["left"], operation),
                                     "right": _with_operation(previous["right"], operation)}
            entry["cancel"] = {"left": _cancel_index(previous["left"], operation),
                               "right": _cancel_index(previous["right"], operation)}
        plan_steps.append(entry)

    plan: dict = {
        "version": PLAN_VERSION, "title": str(scene.get("title") or ""), "rhythm": rhythm, "steps": plan_steps,
        "solutionKind": check.get("solutionKind"), "verification": None, "warnings": warnings, "timing": "voice",
    }
    spoken = _spoken_tokens(words)
    anchors: list[dict | None] = [None]
    cursor = 0
    for index in range(1, len(steps_in)):
        found = _anchors_for_step(spoken, steps_in[index], cursor,
                                  steps_in[index + 1] if index + 1 < len(steps_in) else None) if spoken else None
        anchors.append(found)
        if found is None:
            plan["timing"] = "fallback"
            if spoken:
                warnings.append(f"voice_anchor_missing:step{index + 1}")
            break
        cursor = found["end"]
    if plan["timing"] == "voice" and len(steps_in) < 2:
        plan["timing"] = "fallback"

    ops = len(plan_steps) - 1
    prev_end = 0.0
    tail = rhythm["result_hold"] + rhythm["apply_anim"]
    slot = max((duration - tail - 0.6) / ops, 2.6) if ops else 0.0
    for k in range(1, ops + 1):
        a = anchors[k] if plan["timing"] == "voice" else None
        lead = LEAD_SECONDS
        want_op = (a["op"] - lead) if a else 0.4 + (k - 1) * slot
        want_sides = (a["sides"] - lead) if a and "sides" in a else None
        want_apply = (a["result"] - rhythm["apply_lead"]) if a and "result" in a else None
        t_op = max(want_op, prev_end + (rhythm["gap_min"] if k > 1 else 0.0), 0.0)
        if "intermediate" in plan_steps[k]:  # l'opération est écrite des deux côtés avant le résultat
            t_sides = max(want_sides if want_sides is not None else t_op + rhythm["op_to_sides_min"] + 0.2,
                          t_op + rhythm["op_to_sides_min"])
            t_apply = max(want_apply if want_apply is not None else t_sides + rhythm["sides_to_apply_min"] + 0.3,
                          t_sides + rhythm["sides_to_apply_min"])
        else:  # réécriture / étape non décrite : pas d'équation intermédiaire, donc pas d'intervalle « côtés »
            t_sides = t_op
            t_apply = max(want_apply if want_apply is not None else t_op + rhythm["op_in"] + 0.4, t_op + rhythm["op_in"])
        for label, wanted, got in (("op", want_op, t_op), ("sides", want_sides, t_sides), ("apply", want_apply, t_apply)):
            if plan["timing"] == "voice" and wanted is not None and got - wanted > 0.35:
                warnings.append(f"rhythm_tight:step{k + 1}:{label}:+{got - wanted:.2f}s")
        plan_steps[k]["events"] = {"showOp": round(t_op, 3), "sides": round(t_sides, 3), "apply": round(t_apply, 3)}
        prev_end = t_apply + rhythm["apply_anim"]
    if plan_steps:
        plan_steps[0]["events"] = {"show": 0.0}

    needed = prev_end + rhythm["result_hold"]
    final_kind = check.get("solutionKind")
    root = check.get("solution")
    if scene.get("verify") is True and final_kind == "root" and root is not None and plan_steps:
        try:
            substitution = mv.substitution_check(plan_steps[0]["equation"], Fraction(str(root)))
        except (ValueError, ZeroDivisionError):
            substitution = None
        if substitution and substitution["ok"]:
            substitution = {**substitution, "left": side_tex(substitution["left"]), "right": side_tex(substitution["right"])}
            found = _find_phrase(spoken, scene.get("verifySpoken")) if scene.get("verifySpoken") else None
            if found is None:
                found = next(((i, i + 1) for i, (t, *_rest) in enumerate(spoken) if i >= max(cursor, 0) and t in _VERIFY_WORDS), None)
            at = (spoken[found[0]][1] - LEAD_SECONDS) if found else prev_end + rhythm["verify_gap"]
            at = max(at, prev_end + rhythm["verify_gap"])
            if found and at - (spoken[found[0]][1] - LEAD_SECONDS) > 0.35:
                warnings.append(f"rhythm_tight:verify:+{at - (spoken[found[0]][1] - LEAD_SECONDS):.2f}s")
            plan["verification"] = {"label": "Vérification" if language == "fr" else "Check",
                                    "substitution": substitution, "at": round(at, 3)}
            needed = at + rhythm["verify_anim"] + rhythm["result_hold"]
        elif scene.get("verify") is True:
            warnings.append("verification_unavailable")
    plan["neededDuration"] = round(needed, 3)
    if duration and needed > duration + 0.05:
        warnings.append(f"duration_short:{needed - duration:.2f}s")
    return plan


def extra_hold_seconds(scene: dict, words: list[dict] | None, audio_duration: float, language: str = "fr") -> float:
    """Silence à ajouter en fin de bloc pour que le dernier résultat ait son temps de lecture."""
    try:
        plan = build_plan(scene, words, audio_duration, language)
    except Exception:  # noqa: BLE001 — jamais bloquant : le bloc garde sa durée vocale
        return 0.0
    return round(max(0.0, plan["neededDuration"] - audio_duration), 2) if plan["timing"] == "voice" else 0.0
