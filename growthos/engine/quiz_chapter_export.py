"""Safe chapter cut planner for five-level 50-question quizzes.

Inputs are measured FINAL scene timecodes (seconds), not script word-count estimates.
This module intentionally does not crop 16:9 content into Shorts: a dedicated 9:16
re-layout must be rendered separately to preserve answer readability.
"""
from __future__ import annotations

import math

LEVELS = ("EASY", "MEDIUM", "HARD", "EXPERT", "GENIUS")


def chapter_segments(scenes: list[dict]) -> list[dict]:
    """Return contiguous chapter spans from measured question/reveal scenes.

    Each scene has phase, question_number, start, end. Intro/outro are ignored.
    Reject missing/overlapping scenes rather than exporting inaccurate clips.
    """
    if not isinstance(scenes, list):
        raise ValueError("scenes must be a list")
    relevant = [s for s in scenes if s.get("phase") in {"question", "reveal"}]
    if len(relevant) != 100:
        raise ValueError("five-level quiz requires exactly 50 question/reveal pairs")
    segments = []
    previous_end = None
    for index, scene in enumerate(relevant):
        number = index // 2 + 1
        phase = "question" if index % 2 == 0 else "reveal"
        if scene.get("phase") != phase or scene.get("question_number") != number:
            raise ValueError(f"invalid phase or order at scene {index}")
        start, end = scene.get("start"), scene.get("end")
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)):
            raise ValueError("timecodes must be finite numbers")
        if start < 0 or end <= start or (previous_end is not None and abs(start - previous_end) > .05):
            raise ValueError("invalid or discontinuous timecodes")
        previous_end = end
        if index % 20 == 0:
            segments.append({"chapter": len(segments) + 1, "label": LEVELS[len(segments)],
                             "first_question": number, "last_question": number + 9,
                             "start": start, "end": end})
        else:
            segments[-1]["end"] = end
    return segments
