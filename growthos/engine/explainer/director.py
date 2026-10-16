"""Réalisateur : narration + timing des mots -> storyboard JSON validé (`schema.py`), ancres vérifiées dans la narration.

Un seul appel (Claude Opus par défaut) plus au plus `MAX_REPAIRS` corrections ciblées : si le storyboard est invalide ou
si une ancre n'existe pas dans la narration du plan, les problèmes exacts sont renvoyés au réalisateur.
"""
from __future__ import annotations

import json

from . import llm, prompts, schema, timeline

MAX_REPAIRS = 2


def narration_brief(topic: str, narration: list[tuple[float, str]]) -> str:
    rows = "\n".join(f"[{i}] ({start:.1f} s) {text}" for i, (start, text) in enumerate(narration))
    return f"Sujet de la vidéo : {topic}\n\nNarration (indice, instant de début, texte) :\n{rows}\n"


def anchor_problems(storyboard: dict, narration: list[tuple[float, str]], words: list[dict], total: float) -> list[str]:
    problems = []
    for plan, window in zip(storyboard["plans"], timeline.plan_windows(storyboard, narration, total)):
        _, unresolved = timeline.resolve_anchors(plan, window, words)
        problems += [f"ancre introuvable dans la narration du plan : {u} (le texte doit exister tel quel dans les lignes {plan['lines']})" for u in unresolved]
    return problems


def direct(spend: llm.Spend, topic: str, narration: list[tuple[float, str]], words: list[dict], total: float) -> dict:
    system = prompts.load("director")
    user = narration_brief(topic, narration)
    last_text, problems = "", []
    for attempt in range(MAX_REPAIRS + 1):
        prompt = user if not problems else (
            user + "\nTa proposition précédente :\n```json\n" + last_text + "\n```\nElle a ces problèmes, corrige exactement ceux-là et renvoie le storyboard complet :\n- "
            + "\n- ".join(problems))
        text = llm.complete(spend, f"director#{attempt + 1}", llm.DIRECTOR_MODEL, system, prompt, max_tokens=12000, effort="medium")
        try:
            storyboard = llm.extract_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            problems, last_text = [f"JSON invalide : {exc}"], text[:6000]
            continue
        problems = schema.validate_storyboard(storyboard, len(narration))
        if not problems:
            problems = anchor_problems(storyboard, narration, words, total)
            if problems and attempt == MAX_REPAIRS:
                # Jamais bloquant : une ancre introuvable tombe sur le début de la 1re ligne du plan
                # (timeline.resolve_anchors) et reste écrite au rapport (`unresolvedAnchors`).
                return {"storyboard": storyboard, "attempts": attempt + 1, "anchorWarnings": problems}
        if not problems:
            return {"storyboard": storyboard, "attempts": attempt + 1}
        last_text = json.dumps(storyboard, ensure_ascii=False)
    raise RuntimeError("le réalisateur n'a pas produit de storyboard valide : " + " | ".join(problems[:5]))
