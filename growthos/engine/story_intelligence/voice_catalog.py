"""Provider-agnostic character voice selection from the application's existing catalog.

The UI/database owns voice IDs. This module does not invent provider IDs,
query a new catalog or hardcode any character names.
"""
from __future__ import annotations


def resolve_character_voices(story: dict, catalog: list[dict], selections: dict[str, str]) -> dict[str, str]:
    """Map story character IDs to existing active catalog voice IDs.

    Caller must scope catalog to the authenticated tenant and authorized voices.
    """
    if not isinstance(story, dict) or not isinstance(story.get("characters"), list):
        raise ValueError("Story must contain characters")
    if not isinstance(catalog, list) or not isinstance(selections, dict):
        raise ValueError("Invalid catalog or selections")
    available = {}
    for item in catalog:
        if not isinstance(item, dict):
            raise ValueError("Catalog entries must be objects")
        voice_id = item.get("id")
        if not isinstance(voice_id, str) or not voice_id.strip():
            raise ValueError("Catalog voice ID must be nonempty")
        if voice_id in available:
            raise ValueError("Duplicate catalog voice ID")
        if item.get("enabled", True):
            available[voice_id] = item
    character_ids = [c.get("id") for c in story["characters"] if isinstance(c, dict)]
    if len(character_ids) != len(story["characters"]) or any(not isinstance(cid, str) or not cid.strip() for cid in character_ids):
        raise ValueError("Invalid story character IDs")
    if len(set(character_ids)) != len(character_ids):
        raise ValueError("Duplicate story character IDs")
    if set(selections) != set(character_ids):
        raise ValueError("Select one catalog voice for each character")
    resolved = {}
    for cid in character_ids:
        selected = selections[cid]
        if not isinstance(selected, str) or selected not in available:
            raise ValueError(f"Voice unavailable for character {cid}")
        resolved[cid] = selected
    return resolved
