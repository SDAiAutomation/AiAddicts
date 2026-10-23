"""Story Studio -> contrat de blocs historique (compilation pure, hors ligne).

Un storyboard `content_format: "story"` (validé par `story_intelligence.validator`) est traduit en blocs narrables
comme le fait `quiz.compile_quiz` : une scène = un bloc dont le texte est le dialogue, la voix celle du personnage
qui parle, et l'image montre ce personnage (fiche `characters`, déjà injectée par `image_character_bible`).

Ce module n'appelle AUCUN service (ni ElevenLabs, ni OpenAI) et n'est PAS encore branché dans `script.normalize_script` :
un projet Story ne devient donc pas rendable tant que ce branchement n'a pas été décidé et revu. `estimate()` donne
l'ordre de grandeur de ce que coûterait un rendu, sans rien déclencher.
"""
from __future__ import annotations

from copy import deepcopy

from .story_intelligence.validator import validate_storyboard

STORY_FORMAT = "story"
# Plafond de scènes d'un premier rendu : une image IA + une synthèse vocale par scène.
MAX_RENDER_SHOTS = 12


def is_story(script: dict) -> bool:
    return isinstance(script, dict) and script.get("content_format") == STORY_FORMAT


def render_errors(script: dict) -> list[str]:
    """Raisons pour lesquelles ce projet ne peut pas être rendu (liste vide = prêt). Pas d'IO."""
    story = script.get("story") if isinstance(script, dict) else None
    if not isinstance(story, dict):
        return ["story is missing"]
    errors = validate_storyboard(story)
    if errors:
        return errors
    if len(story["shots"]) > MAX_RENDER_SHOTS:
        errors.append(f"at most {MAX_RENDER_SHOTS} shots can be rendered")
    for character in story["characters"]:
        cid = character["id"]
        if not str(character.get("voice_id") or "").strip():
            errors.append(f"character {cid} has no voice")
        if not str(character.get("description") or "").strip():
            errors.append(f"character {cid} has no visual description")
        if not str(character.get("name") or "").strip():
            errors.append(f"character {cid} has no name")
    return errors


def compile_story(script: dict) -> dict:
    """Copie du script avec `blocks` et `characters` au contrat historique ; lève ValueError si non rendable."""
    if not is_story(script):
        return script
    errors = render_errors(script)
    if errors:
        raise ValueError("Story not renderable: " + "; ".join(errors))
    result = deepcopy(script)
    story = result["story"]
    by_id = {c["id"]: c for c in story["characters"]}
    last = len(story["shots"]) - 1
    blocks = []
    for index, shot in enumerate(story["shots"]):
        speaker = by_id[shot["speaker_id"]]
        blocks.append({
            "role": "hook" if index == 0 else ("cta" if index == last and last > 0 else "point"),
            "text": shot["dialogue"].strip(),
            "voice_id": speaker["voice_id"],
            "speaker_id": speaker["id"],
            "visual": f"{speaker['name']} speaking, illustrated character shot",
            "story_shot_id": shot["id"],
        })
    result["blocks"] = blocks
    result["characters"] = [
        {"name": c["name"], "description": c["description"], **({"negative": c["negative"]} if c.get("negative") else {})}
        for c in story["characters"]
    ]
    return result


def estimate(script: dict) -> dict:
    """Ordre de grandeur d'un rendu (quantités, pas des euros). Estimation : jamais une facture."""
    story = (script or {}).get("story") or {}
    shots = story.get("shots") or []
    return {
        "shots": len(shots),
        "voice_characters": sum(len(str(s.get("dialogue", "")).strip()) for s in shots if isinstance(s, dict)),
        "images": len(shots),
        "estimated": True,
    }
