"""Deterministic, offline timeline planner for Story Studio animation experiments.

This module is intentionally independent of the production worker and providers.
It makes no network calls and never reads credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

MAX_SHOTS = 12
MAX_DURATION_S = 120.0
ALLOWED_ACTIONS = frozenset({"idle", "talk", "gesture", "nod", "blink", "look", "walk", "react"})
ALLOWED_EMOTIONS = frozenset({"neutral", "happy", "sad", "surprised", "angry"})


@dataclass(frozen=True)
class TimedShot:
    shot_id: str
    speaker_id: str
    start_ms: int
    end_ms: int
    action: str
    emotion: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def build_timeline(plan: dict[str, Any]) -> tuple[TimedShot, ...]:
    """Validate a tiny animation plan and return a contiguous millisecond timeline.

    Only IDs and predefined actions are accepted. Paths, URLs, code, arbitrary
    engine commands and untrusted filenames are deliberately unsupported.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    characters = plan.get("characters")
    shots = plan.get("shots")
    if not isinstance(characters, list) or not (1 <= len(characters) <= 4):
        raise ValueError("characters must contain 1-4 entries")
    ids = []
    for character in characters:
        if not isinstance(character, dict):
            raise ValueError("invalid character")
        ident = character.get("id")
        if not isinstance(ident, str) or not ident.isidentifier() or len(ident) > 32:
            raise ValueError("invalid character id")
        ids.append(ident)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate character id")
    if not isinstance(shots, list) or not (1 <= len(shots) <= MAX_SHOTS):
        raise ValueError("invalid shot count")

    cursor = 0
    result = []
    seen = set()
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("invalid shot")
        shot_id = shot.get("id")
        speaker = shot.get("speaker_id")
        duration = shot.get("duration_s")
        action = shot.get("action", "talk")
        emotion = shot.get("emotion", "neutral")
        if not isinstance(shot_id, str) or not shot_id.isidentifier() or len(shot_id) > 32 or shot_id in seen:
            raise ValueError("invalid or duplicate shot id")
        if speaker not in ids:
            raise ValueError("unknown speaker")
        if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not isfinite(duration) or not 0.25 <= duration <= 30:
            raise ValueError("invalid duration")
        if action not in ALLOWED_ACTIONS or emotion not in ALLOWED_EMOTIONS:
            raise ValueError("unsupported animation instruction")
        end = cursor + round(duration * 1000)
        if end > MAX_DURATION_S * 1000:
            raise ValueError("animation too long")
        result.append(TimedShot(shot_id, speaker, cursor, end, action, emotion))
        cursor = end
        seen.add(shot_id)
    return tuple(result)


def frame_state(timeline: tuple[TimedShot, ...], time_ms: int) -> dict[str, Any]:
    """Return a renderer-neutral state; the last frame is inclusive."""
    if not timeline or not isinstance(time_ms, int) or isinstance(time_ms, bool):
        raise ValueError("invalid frame request")
    if time_ms < 0 or time_ms > timeline[-1].end_ms:
        raise ValueError("frame outside timeline")
    shot = next((s for s in timeline if time_ms < s.end_ms), timeline[-1])
    return {"shot_id": shot.shot_id, "speaker_id": shot.speaker_id,
            "action": shot.action, "emotion": shot.emotion,
            "progress": min(1.0, (time_ms - shot.start_ms) / shot.duration_ms)}
