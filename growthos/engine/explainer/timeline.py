"""Timeline globale de mots et résolution des ancres du storyboard.

Sans voix réelle (ElevenLabs hors quota, test hors ligne), `estimate_narration` fabrique des timings PLAUSIBLES au
nombre de caractères : ils servent à écrire et valider les plans, et sont remplacés par les vrais timings du rapport
`voiceover.report.json` (`narration_from_report`) dès que la voix existe. L'appariement des mots réutilise les
fonctions de `engine/motion_graphics/sync.py` (élisions, accents) au lieu de les dupliquer.
"""
from __future__ import annotations

from engine.motion_graphics import sync

CHARS_PER_SECOND = 14.5   # débit de parole moyen estimé (fr), AUCUNE mesure de voix réelle
LINE_GAP = 0.35
LEAD_IN = 0.4
TAIL = 1.2


def estimate_narration(lines: list[str]) -> tuple[list[tuple[float, str]], list[dict]]:
    """Renvoie (narration [(début, texte)], mots [{text,start,end,line}]) avec des durées estimées."""
    narration, words, cursor = [], [], LEAD_IN
    for index, text in enumerate(lines):
        duration = max(1.2, len(text) / CHARS_PER_SECOND)
        narration.append((round(cursor, 2), text))
        tokens = text.split()
        total = sum(len(w) + 1 for w in tokens) or 1
        at = cursor
        for token in tokens:
            span = duration * (len(token) + 1) / total
            words.append({"text": token, "start": round(at, 3), "end": round(at + span, 3), "line": index})
            at += span
        cursor += duration + LINE_GAP
    return narration, words


def narration_from_report(report: dict) -> tuple[list[tuple[float, str]], list[dict]]:
    """Vrais timings : lignes et mots (instants absolus) lus dans `voiceover.report.json`."""
    narration = [(line["start"], line["text"]) for line in report["lines"]]
    words = []
    for w in report["words"]:
        line = max((i for i, (start, _) in enumerate(narration) if start <= w["start"] + 1e-6), default=0)
        words.append({**w, "line": line})
    return narration, words


def total_duration(narration: list[tuple[float, str]], words: list[dict]) -> float:
    last_end = max((w["end"] for w in words), default=narration[-1][0] + 2.0)
    return round(last_end + TAIL, 2)


def plan_windows(storyboard: dict, narration: list[tuple[float, str]], total: float) -> list[dict]:
    """Début et durée de chaque plan : de la 1re ligne du plan à la 1re ligne du suivant (dernier : jusqu'à `total`)."""
    plans = storyboard["plans"]
    starts = [0.0 if i == 0 else narration[p["lines"][0]][0] for i, p in enumerate(plans)]
    out = []
    for i, plan in enumerate(plans):
        end = starts[i + 1] if i + 1 < len(plans) else total
        out.append({"id": plan["id"], "start": round(starts[i], 3), "duration": round(max(end - starts[i], 0.8), 3)})
    return out


def _matches(anchor_tokens: list[str], words: list[dict], i: int) -> bool:
    if i + len(anchor_tokens) > len(words):
        return False
    return all(sync._word_matches(tok, words[i + k]["text"]) for k, tok in enumerate(anchor_tokens))


def resolve_anchors(plan: dict, window: dict, words: list[dict]) -> tuple[dict[str, float], list[str]]:
    """Temps LOCAUX (secondes depuis le début du plan) de chaque ancre. Une ancre introuvable tombe sur le début de la
    1re ligne du plan et est listée dans `unresolved` (écrite au rapport, jamais silencieuse)."""
    plan_words = [w for w in words if window["start"] - 1e-6 <= w["start"] < window["start"] + window["duration"]]
    resolved, unresolved = {}, []
    for anchor in plan.get("anchors", []) or []:
        tokens = [t.lower() for t in sync._TOKEN_RE.findall(anchor["text"])]
        hits = [i for i in range(len(plan_words)) if tokens and _matches(tokens, plan_words, i)]
        n = int(anchor.get("occurrence", 1))
        if len(hits) >= n:
            local = plan_words[hits[n - 1]]["start"] - window["start"]
        else:
            local = plan_words[0]["start"] - window["start"] if plan_words else 0.0
            unresolved.append(f"{plan['id']}.{anchor['id']} « {anchor['text']} »")
        resolved[anchor["id"]] = round(max(0.0, min(local, window["duration"] - 0.2)), 3)
    return resolved, unresolved
