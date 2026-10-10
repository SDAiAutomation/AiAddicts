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


_NUMBER_RE = re.compile(r"\d[\d.,\s]*\d|\d")


def digit_keys(text: str) -> list[str]:
    """Nombres d'un texte affiche, reduits a leurs chiffres : « $38,300 » -> « 38300 », « 3 000 » -> « 3000 »."""
    return [d for d in (re.sub(r"\D", "", m.group(0)) for m in _NUMBER_RE.finditer(text or "")) if d]


def item_numbers(scene: dict) -> list[list[str]]:
    """Pour chaque element de `item_texts` (meme ordre), les nombres qu'il affiche : la valeur d'une ligne de donnees
    (jamais son libelle : « Year 5 » n'est pas un montant), les nombres d'une ligne de texte (formule, liste)."""
    kind = scene.get("sceneType")
    if kind in {"timeline", "checklist", "formula"}:
        return [digit_keys(t) for t in item_texts(scene)]
    if kind in {"money_split", "bar_chart", "donut_chart", "compound_growth"}:
        return [digit_keys(str((r or {}).get("displayValue") or "")) for r in scene.get("data") or []]
    if kind == "comparison":
        return [digit_keys(str((scene.get(k) or {}).get("displayValue") or "")) for k in ("optionA", "optionB")]
    return [[] for _ in item_texts(scene)]


def number_index(words: list[dict], digits: str, start: int = 0) -> int | None:
    """Indice du premier mot (a partir de `start`) ou la voix dit ce nombre : chiffres identiques, jetons numeriques
    consecutifs concatenes (« 3 », « 000 » = 3000)."""
    seq = [re.sub(r"\D", "", str(w.get("text") or "")) for w in words]
    for i in range(max(start, 0), len(seq)):
        acc = ""
        for j in range(i, min(i + 4, len(seq))):
            if not seq[j]:
                break
            acc += seq[j]
            if acc == digits:
                return i
            if len(acc) > len(digits):
                break
    return None


def compute_reveals(scene: dict, words: list[dict], duration: float) -> list[float] | None:
    """Normalised reveal time per item, or None if too few items can be tied
    to a spoken word (then the caller keeps the even stagger).

    Un chiffre ne s'affiche jamais avant d'etre dit : un element qui porte une valeur apparait quand la voix la dit
    (le libelle, souvent dit avant ou apres, passe au second plan) ; sans valeur trouvee dans la narration, c'est le
    libelle qui cale. Une correspondance lexicale trompeuse (« year » / « yearly ») est donc ecartee des qu'une
    valeur dite la contredit."""
    items = item_texts(scene)
    numbers = item_numbers(scene)
    if len(items) < 2 or not words or duration <= 0:
        return None
    starts: list[float | None] = []
    cursor = 0  # matches must advance through the narration in item order
    numeric_hits = 0
    for k, text in enumerate(items):
        toks = _tokens(text)
        label_idx = next((wi for wi in range(cursor, len(words))
                          if any(_word_matches(t, str(words[wi].get("text"))) for t in toks)), None)
        value_idx = next((n for n in (number_index(words, d, cursor) for d in (numbers[k] if k < len(numbers) else []))
                          if n is not None), None)
        label_t = float(words[label_idx].get("start") or 0.0) if label_idx is not None else None
        value_t = float(words[value_idx].get("start") or 0.0) if value_idx is not None else None
        if label_t is None and value_t is None:
            starts.append(None)
            continue
        if value_t is not None:
            numeric_hits += 1
        at = value_t if value_t is not None else label_t
        starts.append(at)
        cursor = max(i for i in (label_idx, value_idx) if i is not None) + 1
    matched = [s for s in starts if s is not None]
    if len(matched) / len(items) < MIN_MATCH_RATIO and not numeric_hits:
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
    if scene.get("sceneType") == "big_number" and not isinstance(scene.get("voiceAnchor"), str) and words and duration > 0:
        # Sans `voiceAnchor` ecrit dans le script : le chiffre apparait et se compte quand la voix le dit.
        for digits in digit_keys(str(scene.get("displayValue") or ""))[:1]:
            index = number_index(words, digits)
            if index is not None:
                at = min(max(0.0, float(words[index].get("start") or 0.0) - LEAD_SECONDS) / duration, MAX_REVEAL)
                return {**scene, "_anchor": round(at, 4), "_duration": float(duration)}
    reveals = compute_reveals(scene, words or [], duration)
    if reveals is None:
        return scene
    return {**scene, "_reveals": reveals, "_duration": float(duration)}
