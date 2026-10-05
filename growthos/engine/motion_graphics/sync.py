"""Narration-synced reveals for Motion Graphics scenes.

Before: every list-like scene revealed its items on an even schedule across the
block, then sat static for most of the (7-8 s) block. Now each item appears
when the narrator SAYS it, using the per-word timings the TTS step already
produces (`audio/block-NN.words.json`) — no new API call.

Contract (mirrors the rest of the module: never block the render):
- `attach_reveals` returns the scene unchanged when it can't match enough
  items to spoken words; scenes then use their original even stagger.
- Reveal times are NORMALISED (0..1 of the block duration), the same unit
  every scene animation already uses, stored under private keys
  `_reveals` / `_duration` that never reach the DB (the scene dict is the
  renderer's local copy).
"""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+", re.IGNORECASE)
_STOP = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "at", "for", "with", "your", "you", "is", "are",
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "en", "à", "au", "aux", "ton", "ta", "tes",
}
LEAD_SECONDS = 0.12  # appear just before the word is fully spoken
MAX_REVEAL = 0.92  # the last item must still be visible before the block ends
MIN_MATCH_RATIO = 0.5


def item_texts(scene: dict) -> list[str]:
    """Ordered on-screen items whose entrance can be timed to speech."""
    kind = scene.get("sceneType")
    if kind == "timeline":
        return [str(s) for s in scene.get("steps") or []]
    if kind == "checklist":
        return [str(s) for s in scene.get("items") or []]
    if kind == "formula":
        return [str(s) for s in scene.get("terms") or []]
    if kind in {"money_split", "bar_chart", "donut_chart", "compound_growth"}:
        return [str((r or {}).get("label") or "") for r in scene.get("data") or []]
    if kind == "comparison":
        return [str((scene.get("optionA") or {}).get("label") or ""), str((scene.get("optionB") or {}).get("label") or "")]
    return []


def _tokens(text: str) -> list[str]:
    return [t for t in (w.lower() for w in _TOKEN_RE.findall(text or "")) if t not in _STOP and len(t) >= 2]


def _word_matches(token: str, word: str) -> bool:
    w = "".join(_TOKEN_RE.findall((word or "").lower()))
    if not w:
        return False
    if token == w:
        return True
    return min(len(token), len(w)) >= 4 and (token.startswith(w) or w.startswith(token))


def compute_reveals(scene: dict, words: list[dict], duration: float) -> list[float] | None:
    """Normalised reveal time per item, or None if too few items can be tied
    to a spoken word (then the caller keeps the even stagger)."""
    items = item_texts(scene)
    if len(items) < 2 or not words or duration <= 0:
        return None
    starts: list[float | None] = []
    cursor = 0  # matches must advance through the narration in item order
    for text in items:
        toks = _tokens(text)
        found = None
        for wi in range(cursor, len(words)):
            if any(_word_matches(t, str(words[wi].get("text"))) for t in toks):
                found = wi
                break
        if found is None:
            starts.append(None)
        else:
            starts.append(float(words[found].get("start") or 0.0))
            cursor = found + 1
    matched = [s for s in starts if s is not None]
    if len(matched) / len(items) < MIN_MATCH_RATIO:
        return None
    # Fill gaps: between matched neighbours (or evenly after the last one).
    filled = list(starts)
    n = len(filled)
    for i, s in enumerate(filled):
        if s is not None:
            continue
        prev_i = next((j for j in range(i - 1, -1, -1) if filled[j] is not None), None)
        next_i = next((j for j in range(i + 1, n) if starts[j] is not None), None)
        lo = filled[prev_i] if prev_i is not None else 0.0
        if next_i is not None:
            hi = starts[next_i]
            span = next_i - (prev_i if prev_i is not None else -1)
            filled[i] = lo + (hi - lo) * (i - (prev_i if prev_i is not None else -1)) / span
        else:
            filled[i] = lo + 0.6 * (i - prev_i) if prev_i is not None else 0.3 * i
    out: list[float] = []
    for s in filled:
        t = max(0.0, (s - LEAD_SECONDS)) / duration
        t = min(t, MAX_REVEAL)
        out.append(max(t, out[-1]) if out else t)  # monotonic
    return [round(t, 4) for t in out]


def attach_reveals(scene: dict, words: list[dict] | None, duration: float) -> dict:
    """A copy of `scene` carrying `_reveals`/`_duration` when syncable, else
    `scene` itself."""
    if scene.get("sceneType") == "equation_steps" and duration > 0:
        steps = scene.get("steps") or []
        spoken = [(token, float(word.get("start") or 0.0)) for word in (words or [])
                  for token in _tokens(str(word.get("text") or ""))]
        if steps and all(isinstance(step, dict) and _tokens(str(step.get("spoken") or "")) for step in steps):
            reveals, cursor = [], 0
            for step in steps:
                phrase = _tokens(str(step["spoken"]))
                found = next((i for i in range(cursor, len(spoken) - len(phrase) + 1)
                              if [token for token, _ in spoken[i:i + len(phrase)]] == phrase), None)
                if found is None:
                    break
                reveals.append(round(min(max(0.0, spoken[found][1] - LEAD_SECONDS) / duration, MAX_REVEAL), 4))
                cursor = found + len(phrase)
            if len(reveals) == len(steps):
                return {**scene, "_reveals": reveals, "_duration": float(duration)}
    if scene.get("sceneType") == "big_number" and isinstance(scene.get("voiceAnchor"), str):
        anchor = _tokens(scene["voiceAnchor"])
        spoken = [(token, float(word.get("start") or 0.0)) for word in (words or [])
                  for token in _tokens(str(word.get("text") or ""))]
        if anchor and duration > 0:
            for index in range(len(spoken) - len(anchor) + 1):
                if [token for token, _ in spoken[index:index + len(anchor)]] == anchor:
                    at = min(max(0.0, spoken[index][1] - LEAD_SECONDS) / duration, MAX_REVEAL)
                    return {**scene, "_anchor": round(at, 4), "_duration": float(duration)}
    reveals = compute_reveals(scene, words or [], duration)
    if reveals is None:
        return scene
    return {**scene, "_reveals": reveals, "_duration": float(duration)}
