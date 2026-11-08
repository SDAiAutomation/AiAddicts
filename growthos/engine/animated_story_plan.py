"""Deterministic shot-level planning and budget enforcement for animated stories.

No paid provider calls are made here. Rendering adapters are deliberately separate.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .animated_story import Story, validate_story

@dataclass(frozen=True)
class RenderTask:
    shot_id: str
    cache_key: str
    speaker_voice_id: str | None
    dialogue: str
    duration_seconds: float
    character_reference_ids: tuple[str, ...]
    reference_frame_id: str | None
    motion: str
    location_id: str

@dataclass(frozen=True)
class RenderPlan:
    tasks: tuple[RenderTask, ...]
    estimated_max_cost_usd: float
    estimated_duration_seconds: float

class RenderPlanError(ValueError):
    pass

def plan_render(story: Story, *, video_usd_per_second: float,
                tts_usd_per_character: float,
                max_budget_usd: float = 5.0) -> RenderPlan:
    """Build an immutable shot plan; reject invalid stories and unaffordable jobs.

    Rates are caller-provided upper bounds, not claims about provider pricing.
    Actual spend must be metered by the executor before each paid request.
    """
    if any(not 0 <= value < 1000 for value in (
        video_usd_per_second, tts_usd_per_character, max_budget_usd
    )):
        raise RenderPlanError("invalid_budget_or_rate")
    validation = validate_story(story)
    if not validation.approved:
        raise RenderPlanError("invalid_story:" + ",".join(validation.errors))
    characters = {c.id: c for c in story.characters}
    tasks = []
    for shot in story.shots:
        references = tuple(characters[c].reference_asset_id for c in shot.characters)
        voice = characters[shot.speaker_id].voice_id if shot.speaker_id else None
        payload = {
            "shot_id": shot.id, "duration": shot.duration_seconds,
            "shot_type": shot.shot_type, "references": references,
            "visual_rules": [characters[c].visual_rules for c in shot.characters],
            "voice": voice, "dialogue": shot.dialogue, "motion": shot.motion,
            "location": shot.location_id, "keyframe": shot.reference_frame_id,
            "version": 1,
        }
        cache_key = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        tasks.append(RenderTask(shot.id, cache_key, voice, shot.dialogue,
                                shot.duration_seconds, references,
                                shot.reference_frame_id, shot.motion, shot.location_id))
    upper_bound = sum(
        shot.duration_seconds * video_usd_per_second
        + len(shot.dialogue) * tts_usd_per_character for shot in story.shots
    )
    if upper_bound > max_budget_usd:
        raise RenderPlanError("budget_exceeded")
    return RenderPlan(tuple(tasks), round(upper_bound, 6), validation.estimated_duration_seconds)
