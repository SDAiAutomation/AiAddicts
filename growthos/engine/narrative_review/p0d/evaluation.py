"""Protocole d'évaluation humaine À L'AVEUGLE des scripts A/B du pilote Standard : plan d'allocation, feuilles pour les auditeurs et les relecteurs, clé de démasquage.

Conforme à `05_EVALUATION_ET_PILOTE.md`, adapté à DEUX variantes (Standard-A, Standard-B) : 12 auditeurs x 5 sujets = 60 évaluations, trois auditeurs par script au minimum.
Les fichiers destinés aux humains ne contiennent QUE des identifiants opaques : ni sujet numéroté, ni condition, ni donnée `evaluator_only`. La correspondance (clé de démasquage) et les
attentes d'évaluateur sont dans un fichier PRIVÉ séparé, ouvert après la saisie. Le critère « un auditeur n'entend jamais deux variantes du même sujet » est garanti par construction.
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
VARIANTS = ("A", "B")


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


def build_packets(campaign_manifest: dict, corpus: dict, out_dir: Path, *, listeners: int = LISTENERS) -> dict:
    """Écrit les feuilles. `campaign_manifest` : celui de la campagne (cases avec identifiants aveugles). Retourne les chemins."""
    blind = {(k["topic_id"], k["condition"]): k["blind_script_id"] for k in campaign_manifest["cases"] if k["stratum"] == "standard"}
    plan = allocate(listeners, sorted({t for t, _ in blind}))
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    files["listener_sheets.csv"] = _csv(["listener_id", "position", "blind_script_id"],
                                        [[p["listener"], p["position"], blind[(p["topic_id"], p["variant"])]] for p in plan])
    files["scores_template.csv"] = _csv(["listener_id", "blind_script_id", *RUBRIC, "central_idea_free_answer", "comprehension_code", *DEFECT_FIELDS, "notes"],
                                        [[p["listener"], blind[(p["topic_id"], p["variant"])]] + [""] * (len(RUBRIC) + 2 + len(DEFECT_FIELDS) + 1) for p in plan])
    # Relecteurs : 5 paires, côtés gauche/droite alternés par une permutation seedée (pas toujours A à gauche)
    pairs = []
    for i, topic in enumerate(sorted({t for t, _ in blind}), 1):
        flip = int(hashlib.sha256(f"{campaign_manifest['campaign_id']}|{topic}".encode()).hexdigest(), 16) % 2
        left, right = (blind[(topic, "A")], blind[(topic, "B")]) if not flip else (blind[(topic, "B")], blind[(topic, "A")])
        pairs.append([f"P{i:02d}", left, right])
    files["pair_votes_template.csv"] = _csv(["reviewer_id", "pair_id", "left_blind_id", "right_blind_id", "preference_left_right_tie_neither", "reason", *DEFECT_FIELDS],
                                            [[f"R{r + 1}", *p] + [""] * (2 + len(DEFECT_FIELDS)) for r in range(RATERS) for p in pairs])
    files["recall_24h_template.csv"] = _csv(["listener_id", "delay_hours_actual", "recalled_blind_script_ids", "verbatim_recall", "absence_reason"],
                                            [[f"L{r + 1:02d}", "", "", "", ""] for r in range(listeners)])
    key = {"WARNING": "PRIVATE: open only after all scores and votes are entered. Never give this file to listeners, reviewers or the generator/critic.",
           "campaign_id": campaign_manifest["campaign_id"], "blind_to_case": {v: {"topic_id": t, "condition": cond} for (t, cond), v in blind.items()},
           "allocation": plan,
           "comprehension": {t: {"question": corpus["topics"][t]["evaluator_only"].get("comprehension_question"),
                                 "acceptable_answer": corpus["topics"][t]["evaluator_only"].get("acceptable_answer")} for t in sorted({t for t, _ in blind})}}
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    (out_dir / "PRIVATE_unblinding_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {name: out_dir / name for name in [*files, "PRIVATE_unblinding_key.json"]}


def pair_differences(scores: list[dict], key: dict, *, min_raters: int = RATERS) -> list[dict]:
    """Médiane par script puis différence B - A par sujet et dimension (le protocole interdit de traiter les 60 notes comme 60 sujets indépendants).
    `scores` : lignes {blind_script_id, <dimension>: 1..5}. Moins de `min_raters` notes pour un script => paire PROVISOIRE, jamais complétée par une valeur par défaut."""
    by_case = key["blind_to_case"]
    per_script: dict[str, dict[str, list[float]]] = {}
    for row in scores:
        for dim in RUBRIC:
            if row.get(dim) not in (None, ""):
                per_script.setdefault(row["blind_script_id"], {}).setdefault(dim, []).append(float(row[dim]))
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
