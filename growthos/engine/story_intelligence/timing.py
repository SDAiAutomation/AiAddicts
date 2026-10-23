"""Pure, offline scene timing. No TTS requests, storage writes or paid API calls."""
from __future__ import annotations

import copy
import math


def align_storyboard(story: dict, measured_seconds: dict[str, float], pause_seconds: float = 0.25) -> tuple[dict, dict]:
    """Retiming never truncates speech. Measured seconds must come from an external audio probe."""
    if not isinstance(story, dict) or not isinstance(story.get("shots"), list) or not story["shots"]:
        raise ValueError("Storyboard must contain nonempty shots")
    if not isinstance(measured_seconds, dict):
        raise ValueError("Measured durations must be a mapping")
    if isinstance(pause_seconds, bool) or not isinstance(pause_seconds, (int, float)) or not math.isfinite(pause_seconds) or pause_seconds < 0:
        raise ValueError("Invalid pause")
    output = copy.deepcopy(story)
    shots = output["shots"]
    ids = [shot.get("id") for shot in shots]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(ids) != len(set(ids)):
        raise ValueError("Shot IDs must be unique nonempty strings")
    if set(ids) != set(measured_seconds):
        raise ValueError("Missing or unexpected measured shot IDs")
    cursor = 0.0
    for shot in shots:
        audio = measured_seconds[shot["id"]]
        planned = shot.get("duration_s")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in (audio, planned)):
            raise ValueError("Audio and planned durations must be finite positive numbers")
        duration = round(max(planned, audio + pause_seconds), 3)
        shot["start_s"] = round(cursor, 3)
        cursor = round(cursor + duration, 3)
        shot["duration_s"] = duration
        shot["end_s"] = cursor
        shot["measured_audio_duration_s"] = audio
    target = story.get("target_duration_s")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target) or target <= 0:
        raise ValueError("Invalid target duration")
    overrun = round(max(0.0, cursor - target), 3)
    report = {
        "target_duration_s": target,
        "planned_after_alignment_s": cursor,
        "overrun_s": overrun,
        "fits_target": abs(cursor - target) <= 0.05,
        "audio_durations_source": "caller_supplied_unverified",
        "ready_for_render": abs(cursor - target) <= 0.05,
    }
    return output, report
