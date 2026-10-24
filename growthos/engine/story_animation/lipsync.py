"""Mouth classes from measured audio (pure functions, no IO, not wired into the worker).

A frame gets one class: "c" closed, "o" open, "r" round. The text alignment returned by the TTS provider says which
character is spoken at each instant; the audio envelope gates it so that silence always closes the mouth.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from typing import Sequence

OPEN_CHARS = frozenset("aàâäeéèêëiîïy")
ROUND_CHARS = frozenset("oôöuùûüw")
CLOSED_CHARS = frozenset("bmpfv")
SILENCE_GATE = 0.12  # normalised envelope below this keeps the mouth closed


def rms_envelope(samples: Sequence[float], sample_rate: int, fps: float) -> list[float]:
    """RMS of each video frame's audio window (same unit as the samples)."""
    if sample_rate <= 0 or fps <= 0:
        raise ValueError("sample_rate and fps must be positive")
    window = max(1, int(sample_rate / fps))
    out = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        out.append(math.sqrt(sum(float(s) * float(s) for s in chunk) / len(chunk)))
    return out


def normalise(envelope: Sequence[float]) -> list[float]:
    """Divide by the 95th percentile so that loud and quiet voices share one gate."""
    if not envelope:
        return []
    ordered = sorted(envelope)
    ref = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]  # nearest-rank percentile
    if ref <= 0:
        return [0.0] * len(envelope)  # all silent: every mouth stays closed
    return [float(v) / ref for v in envelope]


def _char_class(char: str) -> str:
    c = char.lower()
    if c in OPEN_CHARS:
        return "o"
    if c in ROUND_CHARS:
        return "r"
    if c in CLOSED_CHARS or not c.isalpha():
        return "c"
    return "r"  # other consonants: slightly open


def mouth_classes(envelope: Sequence[float], alignment: dict, fps: float, gate: float = SILENCE_GATE) -> str:
    """One class per frame; `envelope` must already be normalised (see `normalise`)."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        raise ValueError("alignment arrays must have the same length")
    if any(b < a for a, b in zip(starts, ends)) or any(b < a for a, b in zip(starts, starts[1:])):
        raise ValueError("alignment times must be ordered")
    out = []
    for frame, level in enumerate(envelope):
        t = (frame + 0.5) / fps
        k = bisect_right(starts, t) - 1
        cls = _char_class(chars[k]) if 0 <= k < len(chars) and t < ends[k] else "c"
        out.append("c" if level < gate else cls)
    for i in range(1, len(out) - 1):  # a single odd frame reads as a glitch
        if out[i] != out[i - 1] and out[i] != out[i + 1]:
            out[i] = out[i - 1]
    return "".join(out)
