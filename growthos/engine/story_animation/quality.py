"""Automatic quality verdicts on a rendered clip (pure, no IO, not wired into the worker).

The caller measures with ffprobe/ffmpeg and passes plain numbers; this module only decides. A non-empty result means
"needs review", never "publish anyway". Quality verdicts are internal diagnostics, not a promise about audience results.
"""
from __future__ import annotations

import math
import re

MAX_SIZE_BYTES = 40 * 1024 * 1024
DURATION_TOLERANCE_S = 0.1
FADE_ALLOWANCE_S = 0.8     # fades in and out legitimately look black / still
MIN_BLACK_S = 0.15
MIN_FREEZE_S = 0.7
MAX_PEAK_DB = -0.1         # at or above: clipping
MIN_MEAN_DB = -32.0        # below: nearly silent


def parse_blackdetect(text: str) -> list[tuple[float, float]]:
    """`black_start:0 black_end:0.5 black_duration:0.5` lines of ffmpeg's blackdetect -> [(start, end)]."""
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:(\S+)\s+black_end:(\S+)", text)]


def parse_freezedetect(text: str) -> list[tuple[float, float]]:
    """freeze_start / freeze_end pairs of ffmpeg's freezedetect -> [(start, end)]; an unfinished freeze is dropped."""
    starts = [float(x) for x in re.findall(r"freeze_start:\s*(\S+)", text)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*(\S+)", text)]
    return list(zip(starts, ends))


def _outside_fades(intervals, duration, min_len):
    bad = []
    for a, b in intervals:
        a2, b2 = max(a, FADE_ALLOWANCE_S), min(b, duration - FADE_ALLOWANCE_S)
        if b2 - a2 >= min_len:
            bad.append((round(a2, 2), round(b2, 2)))
    return bad


def check_media(report: dict, expected: dict) -> list[str]:
    """`report`: measured {video_duration_s, audio_duration_s, width, height, fps, size_bytes, black: [(a, b)],
    freeze: [(a, b)], mean_volume_db, max_volume_db}. `expected`: {width, height, fps}. Returns problems (empty = pass)."""
    problems: list[str] = []
    for key in ("video_duration_s", "audio_duration_s", "width", "height", "fps", "size_bytes"):
        v = report.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            problems.append(f"{key} is missing or not a positive number")
    if problems:
        return problems
    if abs(report["video_duration_s"] - report["audio_duration_s"]) > DURATION_TOLERANCE_S:
        problems.append(f"video {report['video_duration_s']:.2f}s and audio {report['audio_duration_s']:.2f}s differ by more than {DURATION_TOLERANCE_S}s")
    if (report["width"], report["height"]) != (expected["width"], expected["height"]):
        problems.append(f"resolution {report['width']}x{report['height']} is not {expected['width']}x{expected['height']}")
    if abs(report["fps"] - expected["fps"]) > 0.01:
        problems.append(f"frame rate {report['fps']} is not {expected['fps']}")
    if report["size_bytes"] > MAX_SIZE_BYTES:
        problems.append(f"file is {report['size_bytes'] / 1048576:.1f} MiB, above the {MAX_SIZE_BYTES // 1048576} MiB limit")
    duration = report["video_duration_s"]
    for a, b in _outside_fades(report.get("black") or [], duration, MIN_BLACK_S):
        problems.append(f"black frames between {a}s and {b}s")
    for a, b in _outside_fades(report.get("freeze") or [], duration, MIN_FREEZE_S):
        problems.append(f"frozen picture between {a}s and {b}s")
    peak, mean = report.get("max_volume_db"), report.get("mean_volume_db")
    if isinstance(peak, (int, float)) and peak >= MAX_PEAK_DB:
        problems.append(f"audio peak {peak} dB is clipping")
    if isinstance(mean, (int, float)) and mean < MIN_MEAN_DB:
        problems.append(f"audio mean {mean} dB is almost silent")
    return problems
