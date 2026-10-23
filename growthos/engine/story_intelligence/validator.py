"""Deterministic validation of experimental Story Intelligence storyboards."""
from __future__ import annotations

import math


def validate_storyboard(story: dict) -> list[str]:
    """Return actionable errors; no IO, API calls or mutation."""
    errors = []
    if not isinstance(story, dict):
        return ["story must be an object"]
    target = story.get("target_duration_s")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or target <= 0:
        errors.append("target_duration_s must be finite and positive")
    characters = story.get("characters")
    if not isinstance(characters, list) or not characters:
        errors.append("characters must be a nonempty list")
        characters = []
    character_ids = []
    for i, character in enumerate(characters):
        cid = character.get("id") if isinstance(character, dict) else None
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"characters[{i}].id must be a nonempty string")
        else:
            character_ids.append(cid)
    if len(character_ids) != len(set(character_ids)):
        errors.append("character IDs must be unique")
    shots = story.get("shots")
    if not isinstance(shots, list) or not shots:
        return errors + ["shots must be a nonempty list"]
    shot_ids = []
    cursor = 0.0
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append(f"shots[{i}] must be an object")
            continue
        sid = shot.get("id")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"shots[{i}].id must be a nonempty string")
        else:
            shot_ids.append(sid)
        duration = shot.get("duration_s")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            errors.append(f"shots[{i}].duration_s must be finite and positive")
        else:
            cursor += duration
        speaker = shot.get("speaker_id")
        if speaker not in character_ids:
            errors.append(f"shots[{i}].speaker_id is not a known character")
        dialogue = shot.get("dialogue")
        if not isinstance(dialogue, str) or not dialogue.strip():
            errors.append(f"shots[{i}].dialogue must be nonempty")
    if len(shot_ids) != len(set(shot_ids)):
        errors.append("shot IDs must be unique")
    if isinstance(target, (int, float)) and not isinstance(target, bool) and math.isfinite(target) and target > 0:
        if abs(cursor - target) > 0.05:
            errors.append(f"shot durations sum to {cursor:.3f}s, not target {target:.3f}s")
    return errors
