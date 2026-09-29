"""Reusable animation primitives — pure functions of local progress `t` in
[0, 1] (the scene's own timeline, 0 = first frame, 1 = last frame).

Kept deliberately smooth and restrained (ease-out curves, no bounce/spin/
overshoot gimmicks) per the "premium fintech motion design" brief, and fast
enough for Shorts pacing — most scenes finish their entrance within the
first third of their duration and hold, rather than animating the whole way
through.
"""
from __future__ import annotations

import math
import re


def clamp01(t: float) -> float:
    return min(max(t, 0.0), 1.0)


def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t: float, overshoot: float = 1.25) -> float:
    t = clamp01(t) - 1
    return 1 + (overshoot + 1) * t**3 + overshoot * t**2


def phase(t: float, start: float, end: float) -> float:
    """Remaps the [start, end] slice of `t` to a local [0, 1] progress —
    held at 0 before `start`, 1 after `end`."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp01((t - start) / (end - start))


def fade_in(t: float, start: float = 0.0, end: float = 0.22) -> float:
    return ease_out_cubic(phase(t, start, end))


def slide_up(t: float, start: float = 0.0, end: float = 0.3, distance: float = 36.0) -> float:
    """Pixel Y offset: `distance` (below rest position) down to 0."""
    return distance * (1 - ease_out_cubic(phase(t, start, end)))


def scale_in(t: float, start: float = 0.0, end: float = 0.3, from_scale: float = 0.85) -> float:
    p = ease_out_cubic(phase(t, start, end))
    return from_scale + (1 - from_scale) * p


def count_up(t: float, target: float, start: float = 0.0, end: float = 0.6, from_value: float = 0.0) -> float:
    p = ease_out_cubic(phase(t, start, end))
    return from_value + (target - from_value) * p


def progress_fill(t: float, target_ratio: float, start: float = 0.12, end: float = 0.75) -> float:
    return clamp01(target_ratio) * ease_out_cubic(phase(t, start, end))


def stagger(t: float, index: int, count: int, start: float = 0.05, span: float = 0.55, item_duration: float = 0.35) -> float:
    """Local [0, 1] progress for item `index` of `count` items entering one
    after another across the [start, start + span] window."""
    count = max(count, 1)
    item_start = start + (span * index / count)
    return ease_out_cubic(phase(t, item_start, item_start + item_duration))


def pulse(t: float, start: float, period: float = 0.6, amplitude: float = 0.05) -> float:
    """A gentle 1.0 +/- amplitude oscillation for sparing emphasis (e.g. a
    warning icon), inactive before `start`."""
    if t < start:
        return 1.0
    return 1.0 + amplitude * math.sin((t - start) / period * 2 * math.pi)


_NUMBER_RE = re.compile(r"^(\D*)([\d.,]*)(\D*)$")


def format_like(reference: str, number: float) -> str:
    """Formats `number` to look like `reference` (same prefix/suffix and
    decimal precision) — used to animate a count-up toward a value the script
    already provided as `displayValue`, never a fabricated one."""
    match = _NUMBER_RE.match(reference or "")
    if not match:
        return f"{number:,.0f}"
    prefix, digits, suffix = match.groups()
    decimals = len(digits.split(".")[-1]) if "." in digits else 0
    body = f"{number:,.{decimals}f}" if decimals else f"{round(number):,}"
    return f"{prefix}{body}{suffix}"


def parse_number(text: str) -> float | None:
    """Best-effort numeric value behind a formatted string like "$3,000" —
    used when a scene has `displayValue` but no explicit `value` to count up
    from/to."""
    match = re.search(r"[\d][\d.,]*", text or "")
    if not match:
        return None
    cleaned = match.group(0).replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
