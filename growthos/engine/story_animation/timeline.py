"""Timeline of an animated story from MEASURED audio durations (pure, no IO, not wired into the worker).

The contract's shot durations are estimates; what the renderer plays is computed here from the real audio length of each
line, so cuts, mouths and subtitles always agree with the sound.
"""
from __future__ import annotations

import math

from . import contract, lipsync, subtitles

LEAD_S = 0.5      # silence before the first line
GAP_S = 0.35      # pause between lines
TAIL_S = 2.6      # payoff after the last line


def build_timeline(lines: list[dict], fps: int = 24, lead: float = LEAD_S, gap: float = GAP_S, tail: float = TAIL_S,
                   max_total: float = contract.MAX_DURATION_S) -> dict:
    """`lines`: [{"who", "text", "duration_s" (measured), "alignment" (TTS), "envelope" (normalised per frame)}].
    Returns {"fps", "total", "lines": [{who, text, start, dur, end, mouth}], "subs": [{text, start, end}]}."""
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines must be a nonempty list")
    if fps <= 0:
        raise ValueError("fps must be positive")
    t = lead
    out_lines, chunks = [], []
    for i, line in enumerate(lines):
        dur = line.get("duration_s")
        if isinstance(dur, bool) or not isinstance(dur, (int, float)) or not math.isfinite(dur) or dur <= 0:
            raise ValueError(f"lines[{i}].duration_s must be finite and positive")
        alignment = line["alignment"]
        env = line["envelope"]
        out_lines.append({
            "who": line["who"], "text": line["text"],
            "start": round(t, 3), "dur": round(dur, 3), "end": round(t + dur, 3),
            "mouth": lipsync.mouth_classes(env, alignment, fps),
        })
        chunks += subtitles.chunk_words(subtitles.words_from_alignment(alignment, offset=t))
        t += dur + gap
    total = round(out_lines[-1]["end"] + tail, 3)
    if total > max_total:
        raise ValueError(f"total duration {total}s exceeds the {max_total:.0f}s limit")
    return {"fps": fps, "total": total, "lines": out_lines, "subs": subtitles.remove_overlaps(chunks)}


def shot_cuts(timeline: dict, extra_cuts: tuple = ()) -> list[float]:
    """Cut points: 0, the middle of every pause between two lines, any extra cut inside the payoff, and the end.
    Strictly increasing, so shot i spans [cuts[i], cuts[i+1])."""
    lines = timeline["lines"]
    cuts = [0.0] + [round((lines[i - 1]["end"] + lines[i]["start"]) / 2, 3) for i in range(1, len(lines))]
    for c in sorted(extra_cuts):
        if not cuts[-1] < c < timeline["total"]:
            raise ValueError(f"extra cut {c} must fall after the last cut and before the end")
        cuts.append(round(c, 3))
    cuts.append(timeline["total"])
    return cuts


def active_line(timeline: dict, t: float) -> int:
    """Index of the line being spoken at time t, or -1 in a pause."""
    for i, line in enumerate(timeline["lines"]):
        if line["start"] <= t < line["end"]:
            return i
    return -1


def mouth_at(timeline: dict, who: str, frame: int) -> str:
    """Mouth class of `who` at a frame ("c" when they are not speaking)."""
    t = frame / timeline["fps"]
    for line in timeline["lines"]:
        if line["who"] == who and line["start"] <= t < line["end"]:
            mouth = line["mouth"]
            return mouth[min(int((t - line["start"]) * timeline["fps"]), len(mouth) - 1)]
    return "c"
