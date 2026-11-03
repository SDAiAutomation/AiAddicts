"""Beats of a storyboard render: every spoken line cut into 2-4 s ideas on the MEASURED audio (pure, no IO).

One beat = one idea = one image. Cuts happen at clause / punctuation boundaries and are timed with the provider's
character alignment when it matches the text; otherwise time is shared out in proportion to the characters of the line.
A word is never split, and a short line stays a single beat.
"""
from __future__ import annotations

import math

MIN_BEAT_S = 2.0        # under this a beat is merged with its neighbour (when the line allows it)
MAX_BEAT_S = 4.0        # above this a beat is cut again at clause, then word boundaries
SINGLE_BEAT_MAX_S = 4.6  # a line shorter than this is never cut
TARGET_PIECE_S = 3.0    # length aimed for when a long clause must be cut between words
CLAUSE_END = frozenset(",;:.!?…—–")
SENTENCE_END = frozenset(".!?…")
MIN_SENTENCE_BEAT_S = 1.4  # a whole short sentence may stand alone: a new sentence is a new idea
MIN_SEGMENT_S = 0.6     # shortest picture segment the assembly accepts
CUT_LEAD_S = 0.05       # a cut inside a line lands just before the phrase it illustrates


def char_times(text: str, alignment: dict | None, duration: float) -> list[tuple[float, float]]:
    """(start, end) of every character of `text`, relative to the start of the line."""
    n = len(text)
    if n == 0:
        return []
    al = alignment if isinstance(alignment, dict) else {}
    chars = al.get("characters") or []
    starts = al.get("character_start_times_seconds") or []
    ends = al.get("character_end_times_seconds") or []
    if "".join(chars) == text and len(starts) == n and len(ends) == n:
        try:
            times = [(float(a), float(b)) for a, b in zip(starts, ends)]
        except (TypeError, ValueError):
            times = []
        if times and all(math.isfinite(a) and math.isfinite(b) and 0 <= a <= b for a, b in times):
            return times
    step = duration / n
    return [(i * step, (i + 1) * step) for i in range(n)]


def _span(text: str, times: list, a: int, b: int) -> tuple[int, int] | None:  # noqa: ARG001 - same signature as callers
    """Trimmed [a, b) without surrounding spaces, or None if only spaces."""
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return (a, b) if a < b else None


def _clauses(text: str) -> list[tuple[int, int]]:
    """Character spans ending at a punctuation mark followed by a space (or the end of the line)."""
    spans, a = [], 0
    for k, ch in enumerate(text):
        if ch in CLAUSE_END and (k + 1 == len(text) or text[k + 1].isspace()):
            spans.append((a, k + 1))
            a = k + 1
    if a < len(text):
        spans.append((a, len(text)))
    return spans


def _words(text: str, a: int, b: int) -> list[tuple[int, int]]:
    out, k = [], a
    while k < b:
        while k < b and text[k].isspace():
            k += 1
        start = k
        while k < b and not text[k].isspace():
            k += 1
        if start < k:
            out.append((start, k))
    return out


def _duration(times: list, span: tuple[int, int]) -> float:
    return times[span[1] - 1][1] - times[span[0]][0]


def _cut_between_words(text: str, times: list, span: tuple[int, int]) -> list[tuple[int, int]]:
    """A clause longer than MAX_BEAT_S, cut into roughly equal pieces at word boundaries only."""
    words = _words(text, *span)
    pieces = max(1, math.ceil(_duration(times, span) / TARGET_PIECE_S))
    if len(words) < 2 or pieces == 1:
        return [span]
    pieces = min(pieces, len(words))
    t0, total = times[span[0]][0], _duration(times, span)
    out, first = [], 0
    for p in range(1, pieces):
        goal = t0 + total * p / pieces
        # first word that starts at or after the goal time, never empty pieces
        k = next((i for i in range(first + 1, len(words)) if times[words[i][0]][0] >= goal), None)
        if k is None or k >= len(words):
            break
        out.append((words[first][0], words[k - 1][1]))
        first = k
    out.append((words[first][0], words[-1][1]))
    return out


def split_line(text: str, alignment: dict | None, duration: float) -> list[dict]:
    """[{"text", "start", "end"}] relative to the line start, covering the spoken text in order."""
    text = str(text)
    times = char_times(text, alignment, duration)
    whole = _span(text, times, 0, len(text))
    if whole is None:
        return []
    if duration <= SINGLE_BEAT_MAX_S:
        spans = [whole]
    else:
        spans = []
        for a, b in _clauses(text):
            s = _span(text, times, a, b)
            if s is None:
                continue
            spans += _cut_between_words(text, times, s) if _duration(times, s) > MAX_BEAT_S else [s]
        def short(span: tuple[int, int]) -> bool:
            d = _duration(times, span)
            return d < MIN_BEAT_S and not (text[span[1] - 1] in SENTENCE_END and d >= MIN_SENTENCE_BEAT_S)

        merged: list[tuple[int, int]] = []
        for s in spans:
            if merged and short(merged[-1]) and _duration(times, (merged[-1][0], s[1])) <= MAX_BEAT_S + 0.5:
                merged[-1] = (merged[-1][0], s[1])
            else:
                merged.append(s)
        if len(merged) > 1 and short(merged[-1]) and _duration(times, (merged[-2][0], merged[-1][1])) <= MAX_BEAT_S + 1.0:
            merged[-2:] = [(merged[-2][0], merged[-1][1])]
        spans = merged
    return [{"text": text[a:b], "start": round(times[a][0], 3), "end": round(times[b - 1][1], 3)} for a, b in spans]


def build_beats(lines: list[dict]) -> list[dict]:
    """`lines`: [{"text", "start", "dur", "alignment", "speaker_id", "shot_index"}] in absolute time (the measured
    timeline). Returns beats [{"index", "line_index", "shot_index", "speaker_id", "text", "start", "end", "line_first"}]."""
    beats = []
    for li, line in enumerate(lines):
        pieces = split_line(line["text"], line.get("alignment"), float(line["dur"])) or [
            {"text": str(line["text"]), "start": 0.0, "end": float(line["dur"])}]
        for k, piece in enumerate(pieces):
            beats.append({
                "line_index": li, "shot_index": line.get("shot_index", li), "speaker_id": line.get("speaker_id"),
                "text": piece["text"], "start": round(line["start"] + piece["start"], 3),
                "end": round(line["start"] + min(piece["end"], float(line["dur"])), 3), "line_first": k == 0,
            })
    for i, b in enumerate(beats):
        b["index"] = i
    return beats


def merge_to_cap(beats: list[dict], cap: int) -> list[dict]:
    """At most `cap` beats (the number of images paid for before the credit was reserved): the shortest adjacent pair
    inside one line is merged first, then across lines."""
    if cap < 1:
        raise ValueError("cap must be at least 1")
    out = [dict(b) for b in beats]
    while len(out) > cap:
        best, best_d = None, None
        for same_line in (True, False):
            for i in range(len(out) - 1):
                if same_line and out[i]["line_index"] != out[i + 1]["line_index"]:
                    continue
                d = out[i + 1]["end"] - out[i]["start"]
                if best_d is None or d < best_d:
                    best, best_d = i, d
            if best is not None:
                break
        a, b = out[best], out[best + 1]
        a["text"] = f"{a['text']} {b['text']}"
        a["end"] = b["end"]
        del out[best + 1]
    for i, b in enumerate(out):
        b["index"] = i
    return out


def segments(beats: list[dict], lines: list[dict], total: float) -> list[tuple[float, float]]:
    """Picture span of every beat: the first starts at 0 and the last ends at `total`. A cut between two lines falls in the
    middle of the pause; a cut inside a line lands just before the phrase. Spans never go below MIN_SEGMENT_S."""
    if not beats:
        return []
    cuts = [0.0]
    for prev, beat in zip(beats, beats[1:]):
        if beat["line_index"] != prev["line_index"]:
            c = (lines[prev["line_index"]]["start"] + lines[prev["line_index"]]["dur"] + lines[beat["line_index"]]["start"]) / 2
            c = max(c, prev["end"])
        else:
            c = beat["start"] - CUT_LEAD_S
        cuts.append(max(c, cuts[-1] + MIN_SEGMENT_S))
    if len(beats) * MIN_SEGMENT_S > total:
        raise ValueError("too many beats for the duration of the video")
    cuts.append(total)
    for k in range(len(cuts) - 2, 0, -1):   # the end is fixed: pull earlier cuts back if the forward pass overshot
        cuts[k] = min(cuts[k], cuts[k + 1] - MIN_SEGMENT_S)
    return [(round(a, 3), round(b, 3)) for a, b in zip(cuts, cuts[1:])]
