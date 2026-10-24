"""Subtitle chunks from the TTS character alignment (pure functions, no IO, not wired into the worker)."""
from __future__ import annotations

PUNCTUATION = frozenset("?!.,…;:")
MAX_WORDS = 3
LEAD_S = 0.04
TAIL_S = 0.18
GAP_S = 0.02


def words_from_alignment(alignment: dict, offset: float = 0.0) -> list[tuple[str, float, float]]:
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        raise ValueError("alignment arrays must have the same length")
    words: list[tuple[str, float, float]] = []
    text, start, end = "", None, None
    for ch, a, b in zip(chars, starts, ends):
        if ch.isspace():
            if text:
                words.append((text, offset + start, offset + end))
            text, start = "", None
            continue
        if start is None:
            start = a
        text += ch
        end = b
    if text:
        words.append((text, offset + start, offset + end))
    return words


def chunk_words(words: list[tuple[str, float, float]], max_words: int = MAX_WORDS) -> list[dict]:
    """Groups of at most `max_words`; a lone punctuation mark stays with the previous word."""
    merged: list[tuple[str, float, float]] = []
    for text, a, b in words:
        if merged and all(c in PUNCTUATION for c in text):
            prev = merged[-1]
            merged[-1] = (prev[0] + " " + text, prev[1], b)
        else:
            merged.append((text, a, b))
    groups, current = [], []
    for word in merged:
        current.append(word)
        if len(current) >= max_words or word[0][-1] in PUNCTUATION:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [
        {"text": " ".join(w[0] for w in g), "start": round(g[0][1] - LEAD_S, 3), "end": round(g[-1][2] + TAIL_S, 3)}
        for g in groups
    ]


def remove_overlaps(chunks: list[dict]) -> list[dict]:
    """Chunks never overlap and never end before they start."""
    out = [dict(c) for c in chunks]
    for a, b in zip(out, out[1:]):
        a["end"] = round(min(a["end"], b["start"] - GAP_S), 3)
    for c in out:
        c["start"] = max(0.0, c["start"])
        if c["end"] <= c["start"]:
            c["end"] = round(c["start"] + 0.2, 3)
    return out
