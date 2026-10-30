"""Contrat de plan de récit illustré (`story_plan`, version 1) + validation déterministe.

Tout ce qui vient d'un modèle de langage ou d'une recherche externe est NON FIABLE : `validate_story_plan`
est la porte d'entrée obligatoire avant toute génération payante ou tout rendu. Pur : pas d'IO, pas de réseau.
"""
from __future__ import annotations

import ipaddress
import math
import re
from urllib.parse import urlparse

SCHEMA_VERSION = 1

STORY_TYPES = ("knowledge", "true", "moral", "metaphor")
LANGUAGES = ("fr", "en")
# verified = faits sourcés ; inspired = inspiré d'événements réels, romancé ; fiction = inventé ; metaphor = image symbolique
FACTUALITY = ("verified", "inspired", "fiction", "metaphor")
CLAIM_KINDS = ("fact", "interpretation", "hypothesis", "fiction", "metaphor")
BEATS = ("hook", "setup", "conflict", "development", "revelation", "resolution")
TRANSITIONS = ("cut", "crossfade", "fade")
CAMERAS = ("still", "push_in", "pull_out")
ART_DIRECTIONS = ("editorial_knowledge", "cinematic_story", "conceptual_metaphor")

MIN_SCENES, MAX_SCENES = 6, 14
MIN_DURATION_S, MAX_DURATION_S = 30, 120
MAX_NARRATION_CHARS = 420
MAX_ON_SCREEN_CHARS = 90
MAX_PROMPT_CHARS = 1200
MAX_SOURCES = 12
DURATION_TOLERANCE = 0.25  # écart toléré entre durées prévues et cible, avant calage sur la voix

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_VISUAL_DIRECTION_KEYS = ("understand", "feel", "metaphor", "essentials", "omit", "continuity")
_CHARACTER_KEYS = ("appearance", "proportions", "clothing", "palette", "distinctive")


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\x00" not in value


def is_safe_source_url(url: str) -> bool:
    """Anti-SSRF côté contrat : https uniquement, pas d'identifiants, pas d'hôte local/privé/littéral IP interne.
    Le moteur ne télécharge JAMAIS ces URL ; elles servent à la provenance affichée à l'utilisateur."""
    if not isinstance(url, str) or len(url) > 500:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")) or "." not in host and ":" not in host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


def validate_story_plan(plan: dict) -> list[str]:
    """Erreurs actionnables ; liste vide = plan acceptable pour la génération. Ne modifie rien."""
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    errors: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(plan.get("story_id"), str) or not _ID.fullmatch(plan["story_id"]):
        errors.append("story_id must be a safe 1–64 character identifier")
    story_type = plan.get("story_type")
    if story_type not in STORY_TYPES:
        errors.append(f"story_type must be one of {STORY_TYPES}")
    if plan.get("language") not in LANGUAGES:
        errors.append(f"language must be one of {LANGUAGES}")
    if plan.get("art_direction") not in ART_DIRECTIONS:
        errors.append(f"art_direction must be one of {ART_DIRECTIONS}")
    target = plan.get("target_duration_s")
    if not _num(target) or not MIN_DURATION_S <= target <= MAX_DURATION_S:
        errors.append(f"target_duration_s must be between {MIN_DURATION_S} and {MAX_DURATION_S}")
        target = None
    if not _text(plan.get("title"), 120):
        errors.append("title must be a nonempty string of at most 120 characters")

    factuality = plan.get("factuality")
    if factuality not in FACTUALITY:
        errors.append(f"factuality must be one of {FACTUALITY}")
    errors += _validate_factuality(plan, story_type, factuality)
    source_ids = _validate_sources(plan, errors)
    characters = _validate_characters(plan, errors)
    _validate_scenes(plan, errors, characters, source_ids, story_type, factuality, target)
    return errors


def _validate_factuality(plan: dict, story_type, factuality) -> list[str]:
    rules = {
        "true": ("verified", "inspired"),
        "moral": ("fiction", "inspired"),
        "metaphor": ("metaphor", "fiction"),
        "knowledge": ("verified", "metaphor", "inspired"),
    }
    allowed = rules.get(story_type)
    if allowed and factuality in FACTUALITY and factuality not in allowed:
        return [f"a {story_type} story cannot be classified {factuality!r} (allowed: {allowed})"]
    return []


def _validate_sources(plan: dict, errors: list[str]) -> set[str]:
    sources = plan.get("sources", [])
    ids: set[str] = set()
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        errors.append(f"sources must be a list of at most {MAX_SOURCES} items")
        sources = []
    for i, source in enumerate(sources):
        sid = source.get("id") if isinstance(source, dict) else None
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            errors.append(f"sources[{i}].id must be a safe identifier")
            continue
        if sid in ids:
            errors.append(f"sources[{i}].id is duplicated")
        ids.add(sid)
        if not _text(source.get("title"), 200):
            errors.append(f"sources[{i}].title is required")
        if not is_safe_source_url(source.get("url")):
            errors.append(f"sources[{i}].url must be a public https URL")
    if plan.get("factuality") == "verified" and not ids:
        errors.append("a verified story needs at least one source")
    return ids


def _validate_characters(plan: dict, errors: list[str]) -> dict[str, dict]:
    raw = plan.get("characters", [])
    if not isinstance(raw, list) or len(raw) > 4:
        errors.append("characters must be a list of at most 4 items")
        return {}
    found: dict[str, dict] = {}
    for i, character in enumerate(raw):
        if not isinstance(character, dict):
            errors.append(f"characters[{i}] must be an object")
            continue
        cid = character.get("id")
        if not isinstance(cid, str) or not _ID.fullmatch(cid):
            errors.append(f"characters[{i}].id must be a safe identifier")
            continue
        if cid in found:
            errors.append(f"characters[{i}].id is duplicated")
        found[cid] = character
        if not _text(character.get("name"), 80):
            errors.append(f"characters[{i}].name is required")
        for key in _CHARACTER_KEYS:
            if not _text(character.get(key), 300):
                errors.append(f"characters[{i}].{key} is required (identity contract)")
    return found


def _validate_scenes(plan, errors, characters, source_ids, story_type, factuality, target) -> None:
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not MIN_SCENES <= len(scenes) <= MAX_SCENES:
        errors.append(f"scenes must be a list of {MIN_SCENES}–{MAX_SCENES} items")
        return
    ids: list[str] = []
    beat_order: list[int] = []
    total = 0.0
    for i, scene in enumerate(scenes):
        where = f"scenes[{i}]"
        if not isinstance(scene, dict):
            errors.append(f"{where} must be an object")
            continue
        sid = scene.get("id")
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            errors.append(f"{where}.id must be a safe identifier")
        else:
            ids.append(sid)
        beat = scene.get("beat")
        if beat not in BEATS:
            errors.append(f"{where}.beat must be one of {BEATS}")
        else:
            beat_order.append(BEATS.index(beat))
        if not _text(scene.get("narration"), MAX_NARRATION_CHARS):
            errors.append(f"{where}.narration must be nonempty and at most {MAX_NARRATION_CHARS} characters")
        if not _text(scene.get("visual_intention"), 300):
            errors.append(f"{where}.visual_intention is required")
        if not _text(scene.get("image_prompt"), MAX_PROMPT_CHARS):
            errors.append(f"{where}.image_prompt is required")
        text = scene.get("on_screen_text", "")
        if not isinstance(text, str) or len(text) > MAX_ON_SCREEN_CHARS or "<" in text or "\x00" in text:
            errors.append(f"{where}.on_screen_text must be plain text of at most {MAX_ON_SCREEN_CHARS} characters")
        if not _text(scene.get("emotional_tone"), 60):
            errors.append(f"{where}.emotional_tone is required")
        duration = scene.get("duration_s")
        if not _num(duration) or not 2 <= duration <= 20:
            errors.append(f"{where}.duration_s must be between 2 and 20 seconds")
        else:
            total += duration
        if scene.get("transition") not in TRANSITIONS:
            errors.append(f"{where}.transition must be one of {TRANSITIONS}")
        if scene.get("camera", "still") not in CAMERAS:
            errors.append(f"{where}.camera must be one of {CAMERAS}")
        direction = scene.get("visual_direction")
        if not isinstance(direction, dict) or any(not direction.get(k) for k in _VISUAL_DIRECTION_KEYS):
            errors.append(f"{where}.visual_direction must define {_VISUAL_DIRECTION_KEYS}")
        present = scene.get("characters", [])
        if not isinstance(present, list) or any(c not in characters for c in present):
            errors.append(f"{where}.characters must reference known character ids")
        errors += _validate_claims(where, scene, source_ids, story_type, factuality)
    if len(ids) != len(set(ids)):
        errors.append("scene ids must be unique")
    if beat_order and beat_order != sorted(beat_order):
        errors.append("scene beats must follow the narrative order " + " > ".join(BEATS))
    if beat_order and (beat_order[0] != 0 or beat_order[-1] != len(BEATS) - 1):
        errors.append("the story must open on a hook and close on a resolution")
    if beat_order and set(beat_order) != set(range(len(BEATS))):
        errors.append("every narrative beat must appear at least once")
    if target and total and abs(total - target) > target * DURATION_TOLERANCE:
        errors.append(f"planned scene durations sum to {total:.1f}s, too far from target {target}s")


def _validate_claims(where: str, scene: dict, source_ids: set[str], story_type, factuality) -> list[str]:
    errors: list[str] = []
    kind = scene.get("claim_kind", "fiction" if factuality == "fiction" else "fact")
    if kind not in CLAIM_KINDS:
        return [f"{where}.claim_kind must be one of {CLAIM_KINDS}"]
    if factuality == "fiction" and kind == "fact":
        errors.append(f"{where}: a fictional story cannot present a scene as a fact")
    if factuality == "verified" and kind == "fact":
        refs = scene.get("source_ids", [])
        if not isinstance(refs, list) or not refs or any(r not in source_ids for r in refs):
            errors.append(f"{where}: a verified fact must cite at least one known source")
    quote = scene.get("quote")
    if quote is not None:
        refs = scene.get("quote_source_id")
        if factuality != "fiction" and refs not in source_ids:
            errors.append(f"{where}: a quotation presented as authentic must cite a known source")
        if factuality == "fiction" and scene.get("quote_attributed_to_real_person"):
            errors.append(f"{where}: an invented quotation cannot be attributed to a real person")
    return errors
