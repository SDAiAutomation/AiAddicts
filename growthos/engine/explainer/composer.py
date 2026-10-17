"""Compositeur (mode gabarits) : storyboard -> JSON de gabarits -> code de plan, sans que le modèle écrive de JavaScript.

Un seul appel batché pour TOUS les plans (le prompt système est mis en cache), au lieu d'un appel + retouches + critique par plan
dans le mode « code libre ». Le code de chaque plan est généré ici (`S.template(...)`), puis validé par les mêmes contrôles que
le code libre (statique, essai Chromium, sondes de mise en page). Un plan invalide est corrigé par UN seul appel groupé ; s'il
reste invalide, il tombe sur le repli Pillow, écrit au rapport.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import llm, prompts, validate

# Paramètres de premier niveau autorisés par gabarit (une faute de frappe est une erreur, jamais ignorée en silence).
TEMPLATES: dict[str, dict] = {
    "title": {"required": ["text"], "allowed": ["text", "sub", "t", "color", "hide"]},
    "equation": {"required": ["lines"], "allowed": ["lines", "size"]},
    "bignumber": {"required": ["to"], "allowed": ["from", "to", "t0", "t1", "prefix", "suffix", "decimals", "label", "labelT", "color", "y"]},
    "bars": {"required": ["values"], "allowed": ["values", "labels", "t0", "t1", "title", "readout", "readoutT", "color"]},
    "linechart": {"required": ["values"], "allowed": ["values", "t0", "t1", "title", "xlabel", "ylabel", "ref"]},
    "bullets": {"required": ["items"], "allowed": ["items", "title"]},
    "compare": {"required": ["left", "right"], "allowed": ["left", "right", "t", "step"]},
    "flow": {"required": ["nodes"], "allowed": ["nodes"]},
    "segment": {"required": [], "allowed": ["tCut", "ratio", "aLabel", "bLabel", "tLabels"]},
    "fibonacci": {"required": [], "allowed": ["t0", "t1", "n"]},
    "room": {"required": ["message"], "allowed": ["place", "who", "tag", "contact", "message", "typeFrom", "sendAt", "previous", "receiveAt",
                                                   "reply", "replyFrom", "replyAt", "smileAt", "zoomPhone", "zoomOut"]},
    "journey": {"required": [], "allowed": ["t0", "dur", "label", "labels"]},
}
SCENES = ("room", "journey")                        # scènes types : décor, caméra et grille sont les leurs
GUIDE_OK = ("title", "bignumber", "equation", "segment", "fibonacci")
GUIDE_ALLOWED = ["who", "side", "size", "y", "t", "poses", "say"]
ANCHOR_REF = re.compile(r"^@([a-z0-9_]+)([+-]\d+(?:\.\d+)?)?$")
MAX_REPAIRS = 1


def catalog_text() -> str:
    """Sections « gabarits », « scènes types » et « guide » de la doc du runtime (même source que l'animateur)."""
    api = prompts.load("runtime-api")
    parts = []
    for title in ("## Gabarits de scène", "## Scènes types ILLUSTRÉES", "## Le guide"):
        start = api.index(title)
        end = api.find("\n## ", start + 4)
        parts.append(api[start: end if end != -1 else len(api)].strip())
    return "\n\n".join(parts)


def system_prompt() -> str:
    return prompts.load("composer") + "\n\n# Catalogue\n\n" + catalog_text()


def brief(storyboard: dict, windows: list[dict], anchors: dict[str, dict], narration: list[tuple[float, str]], topic: str) -> str:
    plans = []
    for plan, win in zip(storyboard["plans"], windows):
        plans.append({
            "id": plan["id"], "duree_s": win["duration"], "layout": plan.get("layout", "scene"),
            "narration": " ".join(narration[i][1] for i in plan["lines"]),
            "intention": plan.get("intent"), "visuel": plan.get("visual"),
            "ancres": {a["id"]: {"mot": a["text"], "seconde": anchors[plan["id"]].get(a["id"])} for a in plan.get("anchors", [])},
        })
    return json.dumps({"sujet": topic, "monde": storyboard.get("world", {}), "plans": plans}, ensure_ascii=False, indent=1)


def js_value(value, anchor_ids: set[str], errors: list[str], path: str = "params") -> str:
    """Sérialise en JavaScript ; une chaîne `@ancre(+x)` devient `S.t('ancre')(+x)`."""
    if isinstance(value, str):
        m = ANCHOR_REF.match(value)
        if m:
            if m.group(1) not in anchor_ids:
                errors.append(f"{path} : ancre inconnue « @{m.group(1)} » (ancres du plan : {sorted(anchor_ids) or 'aucune'})")
                return "0"
            return f"S.t({json.dumps(m.group(1))}){m.group(2) or ''}"
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(js_value(v, anchor_ids, errors, f"{path}[{i}]") for i, v in enumerate(value)) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{json.dumps(k)}: {js_value(v, anchor_ids, errors, f'{path}.{k}')}" for k, v in value.items()) + " }"
    errors.append(f"{path} : type non supporté ({type(value).__name__})")
    return "null"


def plan_code(spec: dict, anchor_ids: set[str]) -> tuple[str | None, list[str]]:
    """(code, problèmes) pour un élément {template, params, guide?} de la réponse du compositeur."""
    errors: list[str] = []
    name, params = spec.get("template"), spec.get("params")
    if name not in TEMPLATES:
        return None, [f"gabarit inconnu : {name!r} (gabarits : {sorted(TEMPLATES)})"]
    if not isinstance(params, dict):
        return None, ["params doit être un objet"]
    info = TEMPLATES[name]
    errors += [f"paramètre manquant pour {name} : {k}" for k in info["required"] if k not in params]
    errors += [f"paramètre inconnu pour {name} : {k} (admis : {info['allowed']})" for k in params if k not in info["allowed"]]
    guide = spec.get("guide")
    if guide is not None:
        if name not in GUIDE_OK:
            errors.append(f"pas de guide avec le gabarit {name} (guide admis avec : {list(GUIDE_OK)})")
        elif not isinstance(guide, dict):
            errors.append("guide doit être un objet ou null")
        else:
            errors += [f"paramètre inconnu pour guide : {k} (admis : {GUIDE_ALLOWED})" for k in guide if k not in GUIDE_ALLOWED]
    lines = [] if name in SCENES else ["S.grid(true);"]
    lines.append(f"S.template({json.dumps(name)}, {js_value(params, anchor_ids, errors)});")
    if isinstance(guide, dict) and name in GUIDE_OK:
        lines.append(f"S.template('guide', {js_value(guide, anchor_ids, errors, 'guide')});")
    if name not in SCENES:
        lines.append("S.cam.to(0, S.dur, { x: 540, y: 960, z: 1.04 }, 'io');")
    return ("\n".join(lines) if not errors else None), errors


def _ask(spend: llm.Spend, step: str, user: str) -> dict:
    text = llm.complete(spend, step, llm.COMPOSER_MODEL, system_prompt(), user, max_tokens=8000, effort="medium")
    data = llm.extract_json(text)
    if not isinstance(data.get("plans"), list):
        raise ValueError("la réponse doit contenir « plans » (tableau)")
    return {p.get("id"): p for p in data["plans"] if isinstance(p, dict)}


def _check(job: dict, spec: dict | None) -> dict:
    if not spec:
        return {"ok": False, "code": "", "errors": ["plan absent de la réponse du compositeur"], "warnings": []}
    code, errors = plan_code(spec, set(job["anchors"]))
    if errors:
        return {"ok": False, "code": code or "", "errors": errors, "warnings": []}
    result = validate.validate_plan(code, job["plan_id"], job["duration"], job["anchors"], spec["template"])
    return {"ok": result["ok"], "code": code, "errors": result["errors"], "warnings": result["warnings"]}


def compose_all(spend: llm.Spend, storyboard: dict, windows: list[dict], anchors: dict[str, dict], narration: list[tuple[float, str]],
                topic: str, jobs: list[dict], workers: int = 3) -> list[dict]:
    """Même forme de résultat que `animator.animate_all` : {id, ok, code, attempts, errors, warnings, history}."""
    user = brief(storyboard, windows, anchors, narration, topic)
    history: dict[str, list] = {j["plan_id"]: [] for j in jobs}
    try:
        specs = _ask(spend, "composer#1", user)
    except (llm.BudgetExceeded, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        specs = {}
        for h in history.values():
            h.append({"attempt": 1, "stage": "llm", "errors": [str(exc)[:300]]})
    with ThreadPoolExecutor(max_workers=workers) as pool:
        checks = list(pool.map(lambda j: _check(j, specs.get(j["plan_id"])), jobs))
    results = {j["plan_id"]: {**c, "attempts": 1, "specs": specs.get(j["plan_id"])} for j, c in zip(jobs, checks)}
    for pid, r in results.items():
        history[pid].append({"attempt": 1, "ok": r["ok"], "errors": r["errors"][:8]})
    for attempt in range(MAX_REPAIRS):
        failing = [j for j in jobs if not results[j["plan_id"]]["ok"]]
        if not failing:
            break
        problems = {j["plan_id"]: {"ta_proposition": results[j["plan_id"]]["specs"], "problemes": results[j["plan_id"]]["errors"][:10]} for j in failing}
        repair = user + "\n\nCes plans ont échoué à la validation. Renvoie le JSON COMPLET (un élément par plan, y compris ceux qui étaient valides, inchangés), en corrigeant exactement ces problèmes :\n" \
            + json.dumps(problems, ensure_ascii=False, indent=1)
        try:
            fixed = _ask(spend, f"composer#{attempt + 2}", repair)
        except (llm.BudgetExceeded, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            for j in failing:
                history[j["plan_id"]].append({"attempt": attempt + 2, "stage": "llm", "errors": [str(exc)[:300]]})
            break
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rechecked = list(pool.map(lambda j: _check(j, fixed.get(j["plan_id"])), failing))
        for j, c in zip(failing, rechecked):
            results[j["plan_id"]] = {**c, "attempts": attempt + 2, "specs": fixed.get(j["plan_id"])}
            history[j["plan_id"]].append({"attempt": attempt + 2, "ok": c["ok"], "errors": c["errors"][:8]})
    return [{"id": j["plan_id"], "ok": results[j["plan_id"]]["ok"], "code": results[j["plan_id"]]["code"] if results[j["plan_id"]]["ok"] else results[j["plan_id"]]["code"],
             "attempts": results[j["plan_id"]]["attempts"], "errors": results[j["plan_id"]]["errors"], "warnings": results[j["plan_id"]]["warnings"],
             "history": history[j["plan_id"]]} for j in jobs]
