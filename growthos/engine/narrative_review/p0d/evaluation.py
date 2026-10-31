"""Protocole d'évaluation humaine À L'AVEUGLE des scripts A/B du pilote Standard : plan d'allocation, feuilles pour les auditeurs et les relecteurs, clé de démasquage, validation des saisies.

Conforme à `05_EVALUATION_ET_PILOTE.md`, adapté à DEUX variantes (Standard-A, Standard-B) : 12 auditeurs x 5 sujets = 60 évaluations, trois auditeurs par script au minimum.

SÉPARATION des fichiers (la clé de démasquage ne doit jamais être distribuée) :
- `DISTRIBUTABLE/` : les SEULS fichiers qu'on peut donner à des humains. Identifiants opaques uniquement : ni sujet numéroté, ni condition, ni donnée `evaluator_only`. `assert_distributable_clean`
  le vérifie par construction et peut être rejoué avant tout envoi.
- `PRIVATE/` : la clé de démasquage et les attentes d'évaluateur, ouvertes seulement après la saisie. Le dossier contient un `.gitignore` qui exclut tout, et `build_packets` REFUSE d'écrire dans un
  dépôt git (une clé ne doit pas finir dans un commit).

VALIDATION des saisies : notes entières de 1 à 5, identifiants d'auditeur et de script connus, un script n'est noté que par les auditeurs à qui il a été attribué, un auditeur ne note un script qu'une
fois (doublons refusés), relecteurs uniques par paire. Une saisie invalide n'est jamais corrigée ni ignorée : l'agrégation refuse de s'exécuter.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
from pathlib import Path

from ..harness.corpus import PILOT_IDS

LISTENERS = 12
RATERS = 3
RUBRIC = {
    "narrative_quality": {"label": "Qualité narrative d'ensemble", "1": "Succession de faits sans histoire ni progression ; on décroche.",
                          "3": "Histoire reconnaissable, un passage peu utile ; l'intérêt se maintient par moments.", "5": "Chaque étape fait évoluer l'attente ou la compréhension ; on veut connaître la suite ou la réponse."},
    "causality": {"label": "Causalité", "1": "Contradiction majeure ou résolution arbitraire, sans lien avec ce qui précède.", "3": "Liens secondaires implicites mais reconstructibles.",
                  "5": "Les conséquences et transitions nécessaires sont intelligibles, sans trou ni coïncidence non préparée."},
    "clarity": {"label": "Clarté à l'oreille (une seule écoute)", "1": "Acteurs ou raisonnement impossibles à suivre.", "3": "Une ambiguïté locale, sens global compris.", "5": "Compréhension sans effort ni retour arrière."},
    "payoff": {"label": "Payoff : la promesse du début est-elle tenue ?", "1": "Réponse absente, contredite ou remplacée par une formule ou une morale.",
               "3": "Réponse présente mais peu préparée ou redondante.", "5": "Réponse, choix ou conséquence promis : complets, préparés et spécifiques."},
    "factuality": {"label": "Factualité et honnêteté du mode (fiction / documentaire)", "1": "Fait présenté comme réel alors qu'il est inventé, ou affirmation contredite par le dossier.",
                   "3": "Une affirmation non couverte par le dossier, ou un mode ambigu.", "5": "Tout fait est couvert par le dossier ; la fiction est reconnaissable ; aucune attribution inventée."}}
COMPREHENSION_CODES = {"0": "réponse incorrecte", "1": "partielle sans contradiction centrale", "2": "correcte avec la nuance nécessaire"}
DEFECT_FIELDS = ("defect_code", "severity", "quote_or_moment", "established_or_uncertain", "source_consulted")
SCORE_COLUMNS = ("listener_id", "blind_script_id", *RUBRIC, "central_idea_free_answer", "comprehension_code", *DEFECT_FIELDS, "notes")
PAIR_COLUMNS = ("reviewer_id", "pair_id", "left_blind_id", "right_blind_id", "preference_left_right_tie_neither", "reason", *DEFECT_FIELDS)
PREFERENCES = ("left", "right", "tie", "neither")
VARIANTS = ("A", "B")
PRIVATE_DIR, DISTRIBUTABLE_DIR = "PRIVATE", "DISTRIBUTABLE"
FORBIDDEN_IN_DISTRIBUTABLE = ("condition", "evaluator_only", "variant", "unblinding", "blind_to_case", "standard", "story_visual")


def allocate(listeners: int = LISTENERS, topics=PILOT_IDS) -> list[dict]:
    """Une ligne par (auditeur, sujet) : variante `(r + t) mod 2`, ordre des sujets décalé de `r mod 5` et inversé pour les r impairs. Déterministe."""
    topics = sorted(topics)
    rows = []
    for r in range(listeners):
        order = [(r % len(topics) + i) % len(topics) for i in range(len(topics))]
        if r % 2:
            order.reverse()
        for position, t in enumerate(order, 1):
            rows.append({"listener": f"L{r + 1:02d}", "position": position, "topic_id": topics[t], "variant": VARIANTS[(r + t) % 2]})
    return rows


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def _inside_git_worktree(path: Path) -> bool:
    path = path.resolve()
    return any((p / ".git").exists() for p in [path, *path.parents])


class EvaluationFilesError(RuntimeError):
    pass


def build_packets(campaign_manifest: dict, corpus: dict, out_dir: Path, *, listeners: int = LISTENERS, allow_inside_git: bool = False) -> dict:
    """Écrit `DISTRIBUTABLE/` (à distribuer) et `PRIVATE/` (à garder). Retourne {"distributable": {...}, "private": {...}} (chemins)."""
    out_dir = Path(out_dir)
    if not allow_inside_git and _inside_git_worktree(out_dir):
        raise EvaluationFilesError("refusing to write the unblinding key inside a git working tree: choose a folder outside any repository")
    blind = {(k["topic_id"], k["condition"]): k["blind_script_id"] for k in campaign_manifest["cases"] if k["stratum"] == "standard"}
    plan = allocate(listeners, sorted({t for t, _ in blind}))
    dist, priv = out_dir / DISTRIBUTABLE_DIR, out_dir / PRIVATE_DIR
    dist.mkdir(parents=True, exist_ok=True)
    priv.mkdir(parents=True, exist_ok=True)
    files = {}
    files["listener_sheets.csv"] = _csv(["listener_id", "position", "blind_script_id"], [[p["listener"], p["position"], blind[(p["topic_id"], p["variant"])]] for p in plan])
    files["scores_template.csv"] = _csv(list(SCORE_COLUMNS), [[p["listener"], blind[(p["topic_id"], p["variant"])]] + [""] * (len(SCORE_COLUMNS) - 2) for p in plan])
    pairs = []
    for i, topic in enumerate(sorted({t for t, _ in blind}), 1):   # côtés gauche/droite mélangés par une permutation seedée (A n'est pas toujours à gauche)
        flip = int(hashlib.sha256(f"{campaign_manifest['campaign_id']}|{topic}".encode()).hexdigest(), 16) % 2
        left, right = (blind[(topic, "A")], blind[(topic, "B")]) if not flip else (blind[(topic, "B")], blind[(topic, "A")])
        pairs.append([f"P{i:02d}", left, right])
    files["pair_votes_template.csv"] = _csv(list(PAIR_COLUMNS), [[f"R{r + 1}", *p] + [""] * (len(PAIR_COLUMNS) - 4) for r in range(RATERS) for p in pairs])
    files["recall_24h_template.csv"] = _csv(["listener_id", "delay_hours_actual", "recalled_blind_script_ids", "verbatim_recall", "absence_reason"],
                                            [[f"L{r + 1:02d}", "", "", "", ""] for r in range(listeners)])
    key = {"WARNING": "PRIVATE: open only after all scores and votes are entered. Never give this folder to listeners, reviewers or the generator/critic.",
           "campaign_id": campaign_manifest["campaign_id"], "blind_to_case": {v: {"topic_id": t, "condition": cond} for (t, cond), v in blind.items()},
           "allocation": plan, "pairs": {p[0]: {"left": p[1], "right": p[2]} for p in pairs},
           "comprehension": {t: {"question": corpus["topics"][t]["evaluator_only"].get("comprehension_question"),
                                 "acceptable_answer": corpus["topics"][t]["evaluator_only"].get("acceptable_answer")} for t in sorted({t for t, _ in blind})}}
    for name, text in files.items():
        (dist / name).write_text(text, encoding="utf-8", newline="\n")
    (dist / "README.txt").write_text("Distribute ONLY this folder. It contains opaque identifiers and blank forms. Do not add any other file here.\n", encoding="utf-8", newline="\n")
    (priv / "unblinding_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (priv / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8", newline="\n")
    (priv / "README.txt").write_text("PRIVATE. Never distribute. Open after all entries are validated.\n", encoding="utf-8", newline="\n")
    assert_distributable_clean(dist, key, corpus)
    return {"distributable": {p.name: p for p in sorted(dist.iterdir())}, "private": {p.name: p for p in sorted(priv.iterdir())}}


def assert_distributable_clean(folder: Path, key: dict, corpus: dict) -> None:
    """Refuse la distribution si un fichier du dossier contient : un sujet numéroté ou son titre, une condition, une donnée `evaluator_only`, le fichier de clé, ou un nom de fichier privé."""
    forbidden = list(FORBIDDEN_IN_DISTRIBUTABLE) + sorted({v["topic_id"] for v in key["blind_to_case"].values()})
    for topic in corpus["topics"].values():
        forbidden.append(topic["generator_input"]["topic"])
        forbidden += [t for t in _leaf_texts(topic["evaluator_only"]) if len(t) >= 12]
    allowed_names = {"listener_sheets.csv", "scores_template.csv", "pair_votes_template.csv", "recall_24h_template.csv", "README.txt"}
    for path in Path(folder).iterdir():
        if path.name not in allowed_names:
            raise EvaluationFilesError(f"unexpected file in the distributable folder: {path.name}")
        text = path.read_text(encoding="utf-8")
        for secret in forbidden:
            if secret.lower() in text.lower():
                raise EvaluationFilesError(f"{path.name} contains a protected value ({secret[:30]!r})")


def _leaf_texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _leaf_texts(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaf_texts(v)


def _is_int_score(text: str) -> bool:
    return text.strip().isdigit() and 1 <= int(text.strip()) <= 5 and str(int(text.strip())) == text.strip()


def parse_scores(csv_text: str, key: dict) -> tuple[list[dict], list[str]]:
    """Analyse la saisie des auditeurs. Retourne (lignes, problèmes). Une note vide est « manquante » (jamais 0) ; tout le reste est strict."""
    problems: list[str] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or list(reader.fieldnames) != list(SCORE_COLUMNS):
        return [], [f"columns must be exactly {list(SCORE_COLUMNS)}"]
    assigned: dict[str, set[str]] = {}
    blind_of = {(m["topic_id"], m["condition"]): b for b, m in key["blind_to_case"].items()}
    for p in key["allocation"]:
        assigned.setdefault(p["listener"], set()).add(blind_of[(p["topic_id"], p["variant"])])
    rows, seen = [], set()
    for n, raw in enumerate(reader, start=2):
        where, listener, script = f"line {n}", (raw["listener_id"] or "").strip(), (raw["blind_script_id"] or "").strip()
        if listener not in assigned:
            problems.append(f"{where}: unknown listener {listener!r}")
        if script not in key["blind_to_case"]:
            problems.append(f"{where}: unknown script {script!r}")
        elif listener in assigned and script not in assigned[listener]:
            problems.append(f"{where}: {listener} was not assigned {script}")
        if (listener, script) in seen:
            problems.append(f"{where}: duplicate evaluation of {script} by {listener}")
        seen.add((listener, script))
        row = {"listener_id": listener, "blind_script_id": script}
        for dim in RUBRIC:
            value = (raw[dim] or "").strip()
            if value == "":
                row[dim] = None
            elif _is_int_score(value):
                row[dim] = int(value)
            else:
                problems.append(f"{where}: {dim} must be an integer from 1 to 5 (got {value!r})")
                row[dim] = None
        code = (raw["comprehension_code"] or "").strip()
        if code not in ("", *COMPREHENSION_CODES):
            problems.append(f"{where}: comprehension_code must be 0, 1 or 2 (got {code!r})")
        row["comprehension_code"] = int(code) if code in COMPREHENSION_CODES else None
        rows.append(row)
    return rows, problems


def parse_pair_votes(csv_text: str, key: dict) -> tuple[list[dict], list[str]]:
    problems: list[str] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None or list(reader.fieldnames) != list(PAIR_COLUMNS):
        return [], [f"columns must be exactly {list(PAIR_COLUMNS)}"]
    rows, seen = [], set()
    for n, raw in enumerate(reader, start=2):
        where, reviewer, pair = f"line {n}", (raw["reviewer_id"] or "").strip(), (raw["pair_id"] or "").strip()
        if not (reviewer.startswith("R") and reviewer[1:].isdigit() and 1 <= int(reviewer[1:]) <= RATERS):
            problems.append(f"{where}: unknown reviewer {reviewer!r}")
        if pair not in key["pairs"]:
            problems.append(f"{where}: unknown pair {pair!r}")
        elif (raw["left_blind_id"], raw["right_blind_id"]) != (key["pairs"][pair]["left"], key["pairs"][pair]["right"]):
            problems.append(f"{where}: sides do not match pair {pair}")
        if (reviewer, pair) in seen:
            problems.append(f"{where}: duplicate vote by {reviewer} on {pair}")   # relecteur unique par paire
        seen.add((reviewer, pair))
        preference = (raw["preference_left_right_tie_neither"] or "").strip()
        if preference not in ("", *PREFERENCES):
            problems.append(f"{where}: preference must be one of {PREFERENCES}")
        rows.append({"reviewer_id": reviewer, "pair_id": pair, "preference": preference or None})
    return rows, problems


def pair_differences(scores: list[dict], key: dict, *, min_raters: int = RATERS) -> list[dict]:
    """Médiane par script puis différence B - A par sujet et dimension (les 60 notes ne sont pas 60 sujets indépendants).

    `scores` : lignes déjà validées (`parse_scores`). Les valeurs sont revalidées ICI : toute note hors 1..5 entier, tout identifiant inconnu ou doublon (auditeur, script) lève `ValueError`.
    Moins de `min_raters` notes pour un script => paire PROVISOIRE (valeur `None`, jamais 0)."""
    by_case = key["blind_to_case"]
    seen = set()
    per_script: dict[str, dict[str, list[float]]] = {}
    for row in scores:
        listener, script = row.get("listener_id"), row.get("blind_script_id")
        if script not in by_case or not isinstance(listener, str) or not listener:
            raise ValueError(f"invalid scores: unknown listener or script ({listener!r}, {script!r})")
        if (listener, script) in seen:
            raise ValueError(f"invalid scores: duplicate evaluation of {script} by {listener}")
        seen.add((listener, script))
        for dim in RUBRIC:
            value = row.get(dim)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
                raise ValueError(f"invalid scores: {dim} must be an integer from 1 to 5 (got {value!r})")
            per_script.setdefault(script, {}).setdefault(dim, []).append(float(value))
    out = []
    for topic in sorted({v["topic_id"] for v in by_case.values()}):
        ids = {v["condition"]: k for k, v in by_case.items() if v["topic_id"] == topic}
        entry = {"topic_id": topic, "provisional": False, "differences_B_minus_A": {}}
        for dim in RUBRIC:
            a, b = per_script.get(ids["A"], {}).get(dim, []), per_script.get(ids["B"], {}).get(dim, [])
            if len(a) < min_raters or len(b) < min_raters:
                entry["provisional"] = True
                entry["differences_B_minus_A"][dim] = None      # donnée manquante : jamais 0
            else:
                entry["differences_B_minus_A"][dim] = statistics.median(b) - statistics.median(a)
        out.append(entry)
    return out
