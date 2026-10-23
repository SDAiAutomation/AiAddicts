"""Opt-in Story Intelligence voice adapter. No calls happen unless explicitly invoked."""
from __future__ import annotations

import math
from pathlib import Path


def measure_audio_files(shot_audio_paths: dict[str, str], *, duration_probe=None) -> dict[str, float]:
    """Probe existing files; the default uses the engine's decoded playback duration.

    This function never invokes paid TTS. An injected probe allows offline tests.
    """
    if not isinstance(shot_audio_paths, dict) or not shot_audio_paths:
        raise ValueError("shot_audio_paths must be a nonempty mapping")
    if duration_probe is None:
        from growthos.engine.tts import get_playback_duration_seconds
        duration_probe = get_playback_duration_seconds
    results = {}
    for shot_id, filename in shot_audio_paths.items():
        if not isinstance(shot_id, str) or not shot_id.strip():
            raise ValueError("Invalid shot ID")
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError(f"Invalid path for {shot_id}")
        path = Path(filename)
        if not path.is_file():
            raise FileNotFoundError(f"Missing audio for {shot_id}")
        duration = duration_probe(str(path))
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Invalid measured duration for {shot_id}")
        results[shot_id] = float(duration)
    return results


def prepare_aligned_storyboard(story: dict, shot_audio_paths: dict[str, str], *, duration_probe=None, pause_seconds: float = 0.25):
    """Validate input, measure actual files and retime without truncating speech."""
    from .validator import validate_storyboard
    from .timing import align_storyboard
    errors = validate_storyboard(story)
    if errors:
        raise ValueError("Invalid storyboard: " + "; ".join(errors))
    measured = measure_audio_files(shot_audio_paths, duration_probe=duration_probe)
    result, report = align_storyboard(story, measured, pause_seconds=pause_seconds)
    report["audio_durations_source"] = "local_audio_files_probed"
    return result, report
