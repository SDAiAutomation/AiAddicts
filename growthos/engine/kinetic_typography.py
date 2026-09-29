"""Lightweight kinetic typography for the `flat_color` ("solid background +
text") visual style — Phase 2 of the Visual Director roadmap, extended in
Phase 2.6 (benchmark fixes).

Deliberately narrow, in priority order — see `build_emphasis_scene`:
1. an explicit `motion_graphic` already present on the block (fully authored
   structured data beats anything this module could infer).
2. the single most prominent currency amount, percentage or grouped number
   ALREADY PRESENT in the block's `visual` OR `text` (no LLM call, nothing
   invented — see the doctrine's "never invent a number the script didn't
   provide", already enforced the same way in `engine/motion_graphics`).
   Both fields are inspected — a populated-but-numberless `visual` no longer
   hides a number that's only in the spoken narration (Phase 2's bug, caught
   by the visual benchmark: `visual` took exclusive priority over `text`,
   which is correct for IMAGE prompts but wrong for number extraction).
3. a short, deterministically derived display phrase (2-6 words) so a block
   with no number still gets SOME intentional on-screen typography instead
   of staying blank — never a semantic rewrite ("SAVE FIRST" from "saving
   should happen before spending" would require real language understanding
   this module doesn't have); just a cleaned-up excerpt of what's already
   written.

When none of the three apply (empty block), this returns `None` — the
caller falls back to today's flat solid-color clip, unchanged.

A richer "before -> after" or "rate -> total" relationship (the compound
example in the product brief, e.g. "$10/day" turning into "$3,650/year")
would require associating two numbers by their semantic role, which a regex
cannot do reliably — that stays a foundation-only gap for a future phase
with real extraction, not attempted here.
"""
from __future__ import annotations

import re

from .motion_graphics import schema as motion_graphics_schema

# Currency (symbol before or after the amount) or a percentage — both are
# unambiguous "this number matters" signals. A bare number with no symbol
# and no thousands grouping is deliberately NOT matched: too noisy (dates,
# counts, ages would all trigger it) for a supposedly meaningful callout.
_CURRENCY_BEFORE = r"[$€£]\s?\d[\d\s.,]*\d|[$€£]\s?\d"
_CURRENCY_AFTER = r"\d[\d\s.,]*\d\s?[$€£]|\d\s?[$€£]"
_PERCENT = r"\d[\d.,]*\s?%"
_GROUPED_NUMBER = r"\b\d{1,3}(?:[,.]\d{3})+\b"  # ex. "3,650" ou "3.650" — grand nombre à part entière

_EMPHASIS_RE = re.compile(f"(?:{_CURRENCY_BEFORE})|(?:{_CURRENCY_AFTER})|(?:{_PERCENT})|(?:{_GROUPED_NUMBER})")


def extract_emphasis_number(text: str) -> str | None:
    """The first currency amount, percentage, or comma/point-grouped number
    found in `text`, exactly as written (no reformatting, no invention) — or
    `None` if nothing matches. Deterministic: same text, same result."""
    if not text:
        return None
    match = _EMPHASIS_RE.search(text)
    return match.group(0).strip() if match else None


# French camera-direction phrasing that `visual` fields are written with
# (see ai-actions.ts::buildBasePrompt) — stripped before judging whether the
# remainder reads as a short display phrase. Longest-first so "plan large de"
# doesn't shadow a later, more specific match.
_CAMERA_PREFIXES = (
    "gros plan sur ", "plan d'ensemble sur ", "plan d'insert sur ",
    "plan rapproché sur ", "plan subjectif sur ", "plan large sur ",
    "plan large de ", "plan moyen sur ", "plan sur ", "plan de ",
)


def _strip_camera_prefix(phrase: str) -> str:
    stripped = phrase.strip()
    lowered = stripped.lower()
    for prefix in _CAMERA_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return stripped


def derive_typography_phrase(visual: str, text: str, max_words: int = 6, narration_words: int = 5) -> str | None:
    """A short (`max_words` or fewer), high-signal, ALL-CAPS phrase for
    on-screen typography — never a semantic rewrite, only a cleaned-up
    excerpt of `visual` or, failing that, the first few words of `text`.
    `None` if both are empty."""
    candidate = _strip_camera_prefix(visual or "")
    if candidate and len(candidate.split()) <= max_words:
        return candidate.rstrip(" .,!?;:").upper()
    words = (text or "").split()[:narration_words]
    if not words:
        return None
    phrase = " ".join(words).rstrip(" .,!?;:")
    return phrase.upper() or None


def build_emphasis_scene(block: dict) -> dict | None:
    """A `motion_graphics` scene dict for this block's kinetic-typography
    overlay, or `None` if nothing usable exists — see the module docstring
    for the three-tier priority. `block` : the full script block (`visual`,
    `text`, and optionally an already-authored `motion_graphic`)."""
    motion_graphic = block.get("motion_graphic")
    if isinstance(motion_graphic, dict) and motion_graphics_schema.validate_scene(motion_graphic):
        return motion_graphic

    visual = str(block.get("visual") or "")
    text = str(block.get("text") or "")
    number = extract_emphasis_number(visual) or extract_emphasis_number(text)
    if number:
        return {"sceneType": "big_number", "displayValue": number}

    phrase = derive_typography_phrase(visual, text)
    if phrase:
        return {"sceneType": "icon_text", "text": phrase}
    return None
