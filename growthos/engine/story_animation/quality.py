"""Automatic quality verdicts on a rendered clip (pure, no IO, not wired into the worker).

The caller measures with ffprobe/ffmpeg and passes plain numbers; this module only decides. Each problem is either
"blocking" (the clip is broken or unusable: it is not delivered and the credit is refunded) or "review" (the clip is
delivered in the existing `quality_check` state so that a human looks before publishing). Quality verdicts are internal
diagnostics, not a promise about audience results.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

MAX_SIZE_BYTES = 40 * 1024 * 1024
DURATION_TOLERANCE_S = 0.1
FADE_ALLOWANCE_S = 0.8     # fades in and out legitimately look black / still
MIN_BLACK_S = 0.15
MIN_FREEZE_S = 0.7
MAX_PEAK_DB = -0.1         # at or above: clipping
MIN_MEAN_DB = -32.0        # below: nearly silent

BLOCKING = "blocking"
REVIEW = "review"


@dataclass(frozen=True)
class Problem:
    kind: str
    severity: str          # BLOCKING or REVIEW
    text: str              # English diagnostic for logs
    text_fr: str           # what the author sees in the library (the existing quality_flags list)
    detail: dict = field(default_factory=dict)


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


def judge_media(report: dict, expected: dict) -> list[Problem]:
    """`report`: measured {video_duration_s, audio_duration_s, width, height, fps, size_bytes, black: [(a, b)],
    freeze: [(a, b)], mean_volume_db, max_volume_db}. `expected`: {width, height, fps}. Empty list = pass."""
    problems: list[Problem] = []
    for key in ("video_duration_s", "audio_duration_s", "width", "height", "fps", "size_bytes"):
        v = report.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            problems.append(Problem("measure", BLOCKING, f"{key} is missing or not a positive number", f"Mesure indisponible : {key}.", {"key": key}))
    if problems:
        return problems
    vd, ad = report["video_duration_s"], report["audio_duration_s"]
    if abs(vd - ad) > DURATION_TOLERANCE_S:
        problems.append(Problem("duration", BLOCKING, f"video {vd:.2f}s and audio {ad:.2f}s differ by more than {DURATION_TOLERANCE_S}s",
                                f"La durée de l'image ({vd:.1f}s) et celle du son ({ad:.1f}s) ne correspondent pas.", {"video": vd, "audio": ad}))
    if (report["width"], report["height"]) != (expected["width"], expected["height"]):
        problems.append(Problem("resolution", BLOCKING, f"resolution {report['width']}x{report['height']} is not {expected['width']}x{expected['height']}",
                                f"Résolution inattendue ({report['width']}×{report['height']}).", {}))
    if abs(report["fps"] - expected["fps"]) > 0.01:
        problems.append(Problem("fps", BLOCKING, f"frame rate {report['fps']} is not {expected['fps']}", f"Cadence inattendue ({report['fps']} i/s).", {}))
    if report["size_bytes"] > MAX_SIZE_BYTES:
        mib = report["size_bytes"] / 1048576
        problems.append(Problem("size", BLOCKING, f"file is {mib:.1f} MiB, above the {MAX_SIZE_BYTES // 1048576} MiB limit", f"Fichier trop lourd ({mib:.0f} Mio).", {}))
    for a, b in _outside_fades(report.get("black") or [], vd, MIN_BLACK_S):
        problems.append(Problem("black", REVIEW, f"black frames between {a}s and {b}s", f"Image noire entre {a}s et {b}s.", {"start": a, "end": b}))
    for a, b in _outside_fades(report.get("freeze") or [], vd, MIN_FREEZE_S):
        problems.append(Problem("freeze", REVIEW, f"frozen picture between {a}s and {b}s", f"Image figée entre {a}s et {b}s.", {"start": a, "end": b}))
    peak, mean = report.get("max_volume_db"), report.get("mean_volume_db")
    if isinstance(peak, (int, float)) and peak >= MAX_PEAK_DB:
        problems.append(Problem("clipping", REVIEW, f"audio peak {peak} dB is clipping", f"Le son sature (crête à {peak} dB).", {"peak": peak}))
    if isinstance(mean, (int, float)) and mean < MIN_MEAN_DB:
        problems.append(Problem("silence", REVIEW, f"audio mean {mean} dB is almost silent", f"Le son est presque inaudible ({mean} dB).", {"mean": mean}))
    return problems


def check_media(report: dict, expected: dict) -> list[str]:
    """English diagnostics for every problem (blocking and review), as a list of strings (empty = pass)."""
    return [p.text for p in judge_media(report, expected)]


def review_fields(review: list[Problem]) -> dict:
    """Fields to write on the content item for a delivered clip: the existing `quality_check` state (human look before
    publication, and no automatic series publication) with the author-facing flags, or a plain `video`."""
    flags = [p.text_fr for p in review][:8]
    if flags:
        return {"status": "quality_check", "quality_flags": flags}
    return {"status": "video", "quality_flags": []}  # clears the flags of a previous run on the same item
