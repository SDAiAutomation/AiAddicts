"""Story Studio animated stories: contract v1, validation only (pure, no IO, not wired into the worker).

An animated story is a `content_format: "story"` script whose `story.version` is 2. It carries `animation_schema_version`
so the schema can evolve without touching legacy stories (version 1, compiled by `story_compile`), Standard or Quiz.
Everything a renderer may use is a closed catalog id: the user and the model propose, the server validates, and no path,
URL or code ever comes from the story. See docs/product/STORY_STUDIO_GATE4_INTEGRATION_PLAN_2026-10-24.md.
"""
from __future__ import annotations

import math
import os
import re

STORY_VERSION = 2
ANIMATION_SCHEMA_VERSION = 1

MOODS = ("neutral", "worry", "angry", "surprise", "joy", "puzzled", "panic")
GESTURES = ("idle", "accuse", "defend", "wring", "indignant", "clutch_head", "point", "hands_on_hips", "shrug", "wave", "run_away")
SHOT_TYPES = ("wide", "medium", "close_up", "insert")
CAMERA_MOVES = ("static", "push_in", "pull_out", "pan_left", "pan_right")
TRANSITIONS = ("cut", "fade")
SIDES = ("left", "center", "right")
FACINGS = ("left", "right")

MAX_CHARACTERS = 6
MAX_SHOTS = 12
MAX_ACTORS_PER_SHOT = 3
MAX_PROPS_PER_SHOT = 3
MAX_DURATION_S = 60.0
MAX_DIALOGUE_CHARS = 1200
MAX_SHOT_DIALOGUE_CHARS = 400
ZOOM_RANGE = (0.8, 4.0)
MAX_BUDGET_USD = 50.0
MAX_RENDER_S = 1800.0
MAX_TTS_CHARS = 4000

# ---- animation_schema_version 2 ("v2.1"): long-form stories, a narrator, editorial provenance. Schema 1 is unchanged. ----
EXTENDED_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (ANIMATION_SCHEMA_VERSION, EXTENDED_SCHEMA_VERSION)
LIMITS = {
    ANIMATION_SCHEMA_VERSION: {"max_shots": MAX_SHOTS, "max_duration": MAX_DURATION_S, "max_dialogue": MAX_DIALOGUE_CHARS},
    # 180 s target + 10 % ; 300 s stays reserved until a render of that length has been measured
    EXTENDED_SCHEMA_VERSION: {"max_shots": 40, "max_duration": 200.0, "max_dialogue": 3600},
}
ABSOLUTE_MAX_DURATION_S = max(v["max_duration"] for v in LIMITS.values())
DURATION_TARGETS = (60, 90, 120, 180)
MIN_FINAL_DURATION_S = 60.0            # no finished Story Studio video is shorter than this
TARGET_TOLERANCE = (0.85, 1.2)         # measured final duration / target: outside this band the clip is flagged for review
# Speech rate: 14 characters per second is the engine's conservative estimate (upper bound on duration); 17.1 was measured on
# the one real generated clip (494 characters in 28.9 s of speech). A script must reach the target at the fast rate and stay
# under 1.3x the target at the slow rate; the measured duration of the final file is what finally decides.
SPEECH_CHARS_PER_SECOND_SLOW = 14.0
SPEECH_CHARS_PER_SECOND_FAST = 17.1
FIXED_SECONDS = 3.1                    # lead-in, pauses and payoff tail
NATURES = ("fact", "interpretation", "hypothesis", "fiction")
GENRES = ("mystery", "suspense", "drama", "emotion", "moral", "comedy", "adventure", "fantasy", "science_fiction", "romance",
          "history", "education", "psychology", "philosophy")
EDITORIAL_KINDS = ("fiction", "educational", "mixed")
VERIFICATIONS = ("primary", "secondary", "unverified")
MAX_SOURCES = 20
MAX_SOURCE_IDS_PER_SHOT = 5

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_STORY_KEYS = {"version", "animation_schema_version", "language", "characters", "shots", "music_id", "style_id", "budget"}
_CHARACTER_KEYS = {"id", "name", "voice_id", "pack_id"}
_SHOT_KEYS = {"id", "setting_id", "shot_type", "camera", "speaker_id", "dialogue", "actors", "transition_in", "intent", "duration_s"}
_CAMERA_KEYS = {"move", "zoom_from", "zoom_to"}
_ACTOR_KEYS = {"character_id", "side", "facing", "mood", "gesture_id", "props"}
_BUDGET_KEYS = {"max_usd", "max_render_s", "max_tts_chars"}
_EXT_STORY_KEYS = {"duration_target_s", "narrator", "editorial"}
_EXT_SHOT_KEYS = {"nature", "source_ids"}
_NARRATOR_KEYS = {"id", "name", "voice_id"}
_EDITORIAL_KEYS = {"genre", "kind", "sources", "disclaimer"}
_SOURCE_KEYS = {"id", "title", "author", "year", "url", "verification"}
_URL = re.compile(r"https://[^\s<>\"']{1,280}")


class AnimationDisabled(RuntimeError):
    """Raised when an animated story reaches a worker whose animation flag is OFF (refuse before any credit is reserved)."""


def animation_enabled() -> bool:
    """Server flag, OFF by default: only an explicit 1/true/yes/on enables the animated path."""
    return os.environ.get("STORY_ANIMATION_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def is_animated(script: dict) -> bool:
    story = script.get("story") if isinstance(script, dict) else None
    return (
        isinstance(script, dict)
        and script.get("content_format") == "story"
        and isinstance(story, dict)
        and story.get("version") == STORY_VERSION
    )


def route_for(script: dict, enabled: bool | None = None) -> str:
    """"legacy" (nothing changes) or "animated". An animated story with the flag OFF raises, so the caller refuses it
    before reserving a credit or calling any provider."""
    if not is_animated(script):
        return "legacy"
    if not (animation_enabled() if enabled is None else enabled):
        raise AnimationDisabled("animated stories are not enabled")
    return "animated"


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_exactly(value, expected: int) -> bool:
    """Equal to `expected` but never a boolean (Python's True == 1; the TypeScript mirror already rejects it)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == expected


def _is_id(value) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _text_ok(value, limit) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and not _CONTROL.search(value)


def validate_animation_story(story: dict, catalog: dict | None = None) -> list[str]:
    """Actionable errors (empty list = valid). `catalog` is the server-side allow-list:
    {"settings": [...], "props": [...], "packs": [...], "music": [...], "styles": [...]}; without it only the structure is checked."""
    if not isinstance(story, dict):
        return ["story must be an object"]
    errors: list[str] = []
    catalog = catalog or {}

    def allowed(kind: str, value) -> bool:
        return kind not in catalog or value in catalog[kind]

    schema_ok = any(_is_exactly(story.get("animation_schema_version"), v) for v in SUPPORTED_SCHEMA_VERSIONS)
    ext = _is_exactly(story.get("animation_schema_version"), EXTENDED_SCHEMA_VERSION)
    lim = LIMITS[EXTENDED_SCHEMA_VERSION if ext else ANIMATION_SCHEMA_VERSION]
    for key in sorted(set(story) - _STORY_KEYS - (_EXT_STORY_KEYS if ext else set())):
        if key in _EXT_STORY_KEYS:
            errors.append(f"story.{key} requires animation_schema_version {EXTENDED_SCHEMA_VERSION}")
        else:
            errors.append(f"story.{key} is not a known field")
    if not _is_exactly(story.get("version"), STORY_VERSION):
        errors.append(f"story.version must be {STORY_VERSION}")
    if not schema_ok:
        errors.append(f"animation_schema_version {story.get('animation_schema_version')!r} is not supported (expected {ANIMATION_SCHEMA_VERSION} or {EXTENDED_SCHEMA_VERSION})")
    language = story.get("language", "fr")
    if not isinstance(language, str) or not re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", language):
        errors.append("story.language must look like 'fr' or 'fr-FR'")
    music = story.get("music_id")
    if music is not None and (not _is_id(music) or not allowed("music", music)):
        errors.append("story.music_id is not an allowed catalog id")
    style = story.get("style_id")
    if style is not None and (not _is_id(style) or not allowed("styles", style)):
        errors.append("story.style_id is not an allowed catalog id")

    characters = story.get("characters")
    ids: list[str] = []
    if not isinstance(characters, list) or not characters:
        errors.append("characters must be a nonempty list")
    elif len(characters) > MAX_CHARACTERS:
        errors.append(f"at most {MAX_CHARACTERS} characters")
    else:
        for i, c in enumerate(characters):
            if not isinstance(c, dict):
                errors.append(f"characters[{i}] must be an object")
                continue
            for key in sorted(set(c) - _CHARACTER_KEYS):
                errors.append(f"characters[{i}].{key} is not a known field")
            if not _is_id(c.get("id")):
                errors.append(f"characters[{i}].id must be a safe 1-64 character identifier")
            else:
                ids.append(c["id"])
            if not _text_ok(c.get("name"), 60):
                errors.append(f"characters[{i}].name must be 1-60 printable characters")
            if not _is_id(c.get("voice_id")):
                errors.append(f"characters[{i}].voice_id must be a safe identifier")
            if not _is_id(c.get("pack_id")) or not allowed("packs", c.get("pack_id")):
                errors.append(f"characters[{i}].pack_id is not an approved pack")
        if len(ids) != len(set(ids)):
            errors.append("character IDs must be unique")

    narrator_id = None
    if ext and "narrator" in story:
        narrator = story["narrator"]
        if not isinstance(narrator, dict):
            errors.append("narrator must be an object")
        else:
            for key in sorted(set(narrator) - _NARRATOR_KEYS):
                errors.append(f"narrator.{key} is not a known field")
            if not _is_id(narrator.get("id")):
                errors.append("narrator.id must be a safe 1-64 character identifier")
            elif narrator["id"] in ids:
                errors.append("narrator.id must differ from every character id")
            else:
                narrator_id = narrator["id"]
            if not _text_ok(narrator.get("name"), 60):
                errors.append("narrator.name must be 1-60 printable characters")
            if not _is_id(narrator.get("voice_id")):
                errors.append("narrator.voice_id must be a safe identifier")

    source_ids: set[str] = set()
    editorial_kind = None
    if ext and "editorial" in story:
        editorial = story["editorial"]
        if not isinstance(editorial, dict):
            errors.append("editorial must be an object")
        else:
            for key in sorted(set(editorial) - _EDITORIAL_KEYS):
                errors.append(f"editorial.{key} is not a known field")
            if "genre" in editorial and editorial["genre"] not in GENRES:
                errors.append(f"editorial.genre must be one of {', '.join(GENRES)}")
            editorial_kind = editorial.get("kind")
            if editorial_kind not in EDITORIAL_KINDS:
                errors.append(f"editorial.kind must be one of {', '.join(EDITORIAL_KINDS)}")
                editorial_kind = None
            if "disclaimer" in editorial and not _text_ok(editorial["disclaimer"], 300):
                errors.append("editorial.disclaimer must be 1-300 printable characters")
            if editorial_kind == "mixed" and "disclaimer" not in editorial:
                errors.append("editorial.disclaimer is required when kind is 'mixed' (the fiction must be announced as fiction)")
            sources = editorial.get("sources", [])
            if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
                errors.append(f"editorial.sources must be a list of at most {MAX_SOURCES} entries")
            else:
                for k, src in enumerate(sources):
                    sw = f"editorial.sources[{k}]"
                    if not isinstance(src, dict):
                        errors.append(f"{sw} must be an object")
                        continue
                    for key in sorted(set(src) - _SOURCE_KEYS):
                        errors.append(f"{sw}.{key} is not a known field")
                    if not _is_id(src.get("id")):
                        errors.append(f"{sw}.id must be a safe 1-64 character identifier")
                    elif src["id"] in source_ids:
                        errors.append(f"{sw}.id is duplicated")
                    else:
                        source_ids.add(src["id"])
                    if not _text_ok(src.get("title"), 200):
                        errors.append(f"{sw}.title must be 1-200 printable characters")
                    if "author" in src and not _text_ok(src["author"], 120):
                        errors.append(f"{sw}.author must be 1-120 printable characters")
                    if "year" in src and (not _is_number(src["year"]) or int(src["year"]) != src["year"] or not -800 <= src["year"] <= 2100):
                        errors.append(f"{sw}.year must be a whole year")
                    if "url" in src and (not isinstance(src["url"], str) or not _URL.fullmatch(src["url"])):
                        errors.append(f"{sw}.url must be an https URL")
                    if src.get("verification") not in VERIFICATIONS:
                        errors.append(f"{sw}.verification must be one of {', '.join(VERIFICATIONS)}")

    target = None
    if ext and "duration_target_s" in story:
        if not any(_is_exactly(story["duration_target_s"], t) for t in DURATION_TARGETS):
            errors.append(f"duration_target_s must be one of {', '.join(str(t) for t in DURATION_TARGETS)}")
        else:
            target = float(story["duration_target_s"])

    shots = story.get("shots")
    if not isinstance(shots, list) or not shots:
        return errors + ["shots must be a nonempty list"]
    if len(shots) > lim["max_shots"]:
        return errors + [f"at most {lim['max_shots']} shots"]
    shot_ids: list[str] = []
    total_chars = 0
    estimated = 0.0
    for i, shot in enumerate(shots):
        where = f"shots[{i}]"
        if not isinstance(shot, dict):
            errors.append(f"{where} must be an object")
            continue
        for key in sorted(set(shot) - _SHOT_KEYS - (_EXT_SHOT_KEYS if ext else set())):
            if key in _EXT_SHOT_KEYS:
                errors.append(f"{where}.{key} requires animation_schema_version {EXTENDED_SCHEMA_VERSION}")
            else:
                errors.append(f"{where}.{key} is not a known field")
        if ext:
            nature = shot.get("nature")
            if "nature" in shot and nature not in NATURES:
                errors.append(f"{where}.nature must be one of {', '.join(NATURES)}")
            refs = shot.get("source_ids", [])
            if not isinstance(refs, list) or len(refs) > MAX_SOURCE_IDS_PER_SHOT or not all(_is_id(r) and r in source_ids for r in refs):
                errors.append(f"{where}.source_ids must list at most {MAX_SOURCE_IDS_PER_SHOT} ids of editorial.sources")
            if nature == "fact" and not refs:
                errors.append(f"{where} states a fact: it needs at least one source_ids entry")
            if editorial_kind == "fiction" and nature in ("fact", "interpretation", "hypothesis"):
                errors.append(f"{where}.nature {nature!r} is not allowed when editorial.kind is 'fiction'")
        if not _is_id(shot.get("id")):
            errors.append(f"{where}.id must be a safe 1-64 character identifier")
        else:
            shot_ids.append(shot["id"])
        if not _is_id(shot.get("setting_id")) or not allowed("settings", shot.get("setting_id")):
            errors.append(f"{where}.setting_id is not an allowed catalog id")
        if shot.get("shot_type") not in SHOT_TYPES:
            errors.append(f"{where}.shot_type must be one of {', '.join(SHOT_TYPES)}")
        camera = shot.get("camera", {"move": "static", "zoom_from": 1.0, "zoom_to": 1.0})
        if not isinstance(camera, dict):
            errors.append(f"{where}.camera must be an object")
        else:
            for key in sorted(set(camera) - _CAMERA_KEYS):
                errors.append(f"{where}.camera.{key} is not a known field")
            if camera.get("move", "static") not in CAMERA_MOVES:
                errors.append(f"{where}.camera.move must be one of {', '.join(CAMERA_MOVES)}")
            for key in ("zoom_from", "zoom_to"):
                v = camera.get(key, 1.0)
                if not _is_number(v) or not ZOOM_RANGE[0] <= v <= ZOOM_RANGE[1]:
                    errors.append(f"{where}.camera.{key} must be between {ZOOM_RANGE[0]} and {ZOOM_RANGE[1]}")
        dialogue = shot.get("dialogue")
        if not _text_ok(dialogue, MAX_SHOT_DIALOGUE_CHARS):
            errors.append(f"{where}.dialogue must be 1-{MAX_SHOT_DIALOGUE_CHARS} printable characters")
        else:
            total_chars += len(dialogue)
        if "intent" in shot and not _text_ok(shot["intent"], 200):
            errors.append(f"{where}.intent must be 1-200 printable characters")
        if shot.get("transition_in", "cut") not in TRANSITIONS:
            errors.append(f"{where}.transition_in must be one of {', '.join(TRANSITIONS)}")
        if "duration_s" in shot:
            d = shot["duration_s"]
            if not _is_number(d) or d <= 0 or d > lim["max_duration"]:
                errors.append(f"{where}.duration_s (estimate) must be finite, positive and at most {lim['max_duration']}")
            else:
                estimated += d
        actors = shot.get("actors")
        actor_ids: list[str] = []
        narrated = narrator_id is not None and shot.get("speaker_id") == narrator_id
        if narrated and isinstance(actors, list) and not actors:
            pass  # a narrator shot may show the setting alone
        elif not isinstance(actors, list) or not actors:
            errors.append(f"{where}.actors must be a nonempty list")
        elif len(actors) > MAX_ACTORS_PER_SHOT:
            errors.append(f"{where} has more than {MAX_ACTORS_PER_SHOT} actors")
        else:
            for j, a in enumerate(actors):
                aw = f"{where}.actors[{j}]"
                if not isinstance(a, dict):
                    errors.append(f"{aw} must be an object")
                    continue
                for key in sorted(set(a) - _ACTOR_KEYS):
                    errors.append(f"{aw}.{key} is not a known field")
                if a.get("character_id") not in ids:
                    errors.append(f"{aw}.character_id is not a known character")
                else:
                    actor_ids.append(a["character_id"])
                if a.get("side") not in SIDES:
                    errors.append(f"{aw}.side must be one of {', '.join(SIDES)}")
                if a.get("facing") not in FACINGS:
                    errors.append(f"{aw}.facing must be one of {', '.join(FACINGS)}")
                if a.get("mood", "neutral") not in MOODS:
                    errors.append(f"{aw}.mood must be one of {', '.join(MOODS)}")
                if a.get("gesture_id", "idle") not in GESTURES:
                    errors.append(f"{aw}.gesture_id must be one of {', '.join(GESTURES)}")
                props = a.get("props", [])
                if not isinstance(props, list) or len(props) > MAX_PROPS_PER_SHOT or not all(_is_id(p) and allowed("props", p) for p in props):
                    errors.append(f"{aw}.props must be at most {MAX_PROPS_PER_SHOT} allowed catalog ids")
            if len(actor_ids) != len(set(actor_ids)):
                errors.append(f"{where} lists the same character twice")
        speaker = shot.get("speaker_id")
        if narrated:
            if shot.get("shot_type") == "close_up":
                errors.append(f"{where}: a narrator shot cannot be a close_up (there is no speaker to frame)")
        elif speaker not in ids:
            errors.append(f"{where}.speaker_id is not a known character" + (" or the narrator" if narrator_id else ""))
        elif actor_ids and speaker not in actor_ids:
            errors.append(f"{where}.speaker_id must also appear in actors (lip-sync needs the speaker on screen)")
    if len(shot_ids) != len(set(shot_ids)):
        errors.append("shot IDs must be unique")
    if total_chars > lim["max_dialogue"]:
        errors.append(f"total dialogue is {total_chars} characters, at most {lim['max_dialogue']}")
    if estimated > lim["max_duration"]:
        errors.append(f"estimated durations sum to {estimated:.1f}s, at most {lim['max_duration']:.0f}s")
    if target is not None and total_chars <= lim["max_dialogue"]:
        fast = total_chars / SPEECH_CHARS_PER_SECOND_FAST + FIXED_SECONDS
        slow = total_chars / SPEECH_CHARS_PER_SECOND_SLOW + FIXED_SECONDS
        floor = max(MIN_FINAL_DURATION_S, TARGET_TOLERANCE[0] * target)
        if fast < floor:
            errors.append(f"the text is too short for a {target:.0f}s target: about {fast:.0f}s at the fast speech rate, at least {floor:.0f}s needed")
        if slow > 1.3 * target:
            errors.append(f"the text is too long for a {target:.0f}s target: about {slow:.0f}s at the slow speech rate, at most {1.3 * target:.0f}s allowed")

    budget = story.get("budget")
    if budget is not None:
        if not isinstance(budget, dict):
            errors.append("budget must be an object")
        else:
            for key in sorted(set(budget) - _BUDGET_KEYS):
                errors.append(f"budget.{key} is not a known field")
            for key, cap in (("max_usd", MAX_BUDGET_USD), ("max_render_s", MAX_RENDER_S), ("max_tts_chars", MAX_TTS_CHARS)):
                if key in budget and (not _is_number(budget[key]) or budget[key] <= 0 or budget[key] > cap):
                    errors.append(f"budget.{key} must be positive and at most {cap}")
    return errors
