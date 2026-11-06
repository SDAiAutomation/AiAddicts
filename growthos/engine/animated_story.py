"""Provider-independent animated story contracts and deterministic validation.

This is a safe foundation, not an animation/video provider integration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ShotType = Literal["establishing", "dialogue", "reaction", "action", "reveal"]
MotionType = Literal["hold", "blink", "head_turn", "gesture", "walk", "camera_pan"]

@dataclass(frozen=True)
class Character:
    id: str
    name: str
    reference_asset_id: str
    voice_id: str
    visual_rules: tuple[str, ...] = ()

@dataclass(frozen=True)
class Shot:
    id: str
    duration_seconds: float
    shot_type: ShotType
    characters: tuple[str, ...]
    location_id: str
    dialogue: str = ""
    speaker_id: str | None = None
    motion: MotionType = "hold"
    reference_frame_id: str | None = None

@dataclass(frozen=True)
class Story:
    id: str
    title: str
    characters: tuple[Character, ...]
    shots: tuple[Shot, ...]
    aspect_ratio: str = "9:16"
    language: str = "fr"

@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    estimated_duration_seconds: float = 0.0
    @property
    def approved(self) -> bool:
        return not self.errors

def validate_story(story: Story, *, max_duration_seconds: float = 90.0) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    ids = [c.id for c in story.characters]
    known = set(ids)
    if len(ids) != len(known):
        errors.append("duplicate_character_id")
    if not story.characters:
        errors.append("missing_characters")
    if not story.shots:
        errors.append("missing_shots")
    if story.aspect_ratio != "9:16":
        errors.append("unsupported_aspect_ratio")
    for character in story.characters:
        if not character.reference_asset_id or not character.voice_id:
            errors.append(f"missing_character_assets:{character.id}")
    shot_ids: set[str] = set()
    for shot in story.shots:
        if shot.id in shot_ids:
            errors.append(f"duplicate_shot_id:{shot.id}")
        shot_ids.add(shot.id)
        if not 0 < shot.duration_seconds <= 15:
            errors.append(f"invalid_shot_duration:{shot.id}")
        if not shot.location_id:
            errors.append(f"missing_location:{shot.id}")
        if set(shot.characters) - known:
            errors.append(f"unknown_character:{shot.id}")
        if shot.speaker_id and (shot.speaker_id not in known or shot.speaker_id not in shot.characters):
            errors.append(f"invalid_speaker:{shot.id}")
        if shot.dialogue and not shot.speaker_id:
            errors.append(f"missing_speaker:{shot.id}")
        if shot.speaker_id and not shot.dialogue.strip():
            warnings.append(f"silent_speaker:{shot.id}")
        if not shot.reference_frame_id:
            warnings.append(f"missing_keyframe:{shot.id}")
    duration = sum(s.duration_seconds for s in story.shots)
    if duration > max_duration_seconds:
        errors.append("duration_exceeded")
    return ValidationResult(tuple(errors), tuple(warnings), duration)
