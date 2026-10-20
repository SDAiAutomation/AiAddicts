"""Safe chapter cut planner for five-level 50-question quizzes.

Inputs are measured FINAL scene timecodes (seconds), not script word-count estimates.
This module intentionally does not crop 16:9 content into Shorts: a dedicated 9:16
re-layout is rendered separately (see engine/quiz_shorts.py) to preserve answer readability.
"""
from __future__ import annotations

import math

LEVELS = ("EASY", "MEDIUM", "HARD", "EXPERT", "GENIUS")


def scenes_from_timeline(report: dict, blocks: list[dict]) -> list[dict]:
    """Adapt `quiz_motion.build_timeline` output (camelCase, per block) to the planner's scene shape."""
    scenes = []
    for scene in report.get("scenes") or []:
        block = blocks[scene["block"]] if 0 <= scene.get("block", -1) < len(blocks) else {}
        scenes.append({"phase": scene.get("phase"), "block": scene.get("block"),
                       "question_number": block.get("quiz_question_number"),
                       "chapter_number": block.get("quiz_chapter_number"),
                       "start": scene.get("startSeconds"), "end": scene.get("endSeconds")})
    return scenes


def _finite(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def chapter_segments(scenes: list[dict]) -> list[dict]:
    """Return contiguous chapter spans from measured chapter/question/reveal scenes.

    Each scene has phase, question_number, start, end. Intro/outro are ignored. When chapter title
    scenes are present each one opens its chapter (and must precede questions 1, 11, 21, 31, 41).
    Reject missing/overlapping scenes rather than exporting inaccurate clips.
    """
    if not isinstance(scenes, list):
        raise ValueError("scenes must be a list")
    relevant = [s for s in scenes if s.get("phase") in {"chapter", "question", "reveal"}]
    cards = [s for s in relevant if s["phase"] == "chapter"]
    if cards and len(cards) != 5:
        raise ValueError("five-level quiz requires exactly 5 chapter scenes")
    if len([s for s in relevant if s["phase"] != "chapter"]) != 100:
        raise ValueError("five-level quiz requires exactly 50 question/reveal pairs")
    segments: list[dict] = []
    previous_end = None
    number = 0
    last_phase = "reveal"  # a question (or card) may open the sequence
    card_start = None
    for scene in relevant:
        start, end, phase = scene.get("start"), scene.get("end"), scene["phase"]
        if not (_finite(start) and _finite(end)):
            raise ValueError("timecodes must be finite numbers")
        if start < 0 or end <= start or (previous_end is not None and abs(start - previous_end) > .05):
            raise ValueError("invalid or discontinuous timecodes")
        previous_end = end
        if phase == "chapter":
            if last_phase != "reveal" or number % 10 != 0 or scene.get("chapter_number") not in (None, number // 10 + 1):
                raise ValueError("chapter scene out of order")
            card_start, last_phase = start, "chapter"
            continue
        if phase == "question":
            if last_phase == "question" or (cards and number % 10 == 0 and last_phase != "chapter"):
                raise ValueError(f"invalid phase order before question {number + 1}")
            number += 1
        elif last_phase != "question":
            raise ValueError(f"reveal without question at question {number}")
        last_phase = phase
        if scene.get("question_number") != number:
            raise ValueError(f"invalid phase or order at question {number}")
        if phase == "question" and (number - 1) % 10 == 0:
            segments.append({"chapter": len(segments) + 1, "label": LEVELS[len(segments)],
                             "first_question": number, "last_question": number + 9,
                             "start": card_start if card_start is not None else start, "end": end,
                             "has_card": card_start is not None})
            card_start = None
        else:
            segments[-1]["end"] = end
    if len(segments) != 5 or number != 50 or last_phase != "reveal":
        raise ValueError("five-level quiz requires five complete chapters")
    return segments
