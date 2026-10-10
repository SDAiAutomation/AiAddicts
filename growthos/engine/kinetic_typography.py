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
3. a short emphasis phrase (2-4 words) taken from the END of the narration
   (`derive_emphasis_phrase`): the last clause, never starting on a
   function word, never the whole sentence. Narration only: `visual` is an
   image/camera direction and is never shown to the viewer. Nothing is
   invented or rewritten; when no phrase adds anything beyond the captions the
   block gets no kinetic text.

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
import unicodedata

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


# Mots-outils fr + en (sans accents : les scripts les omettent souvent). Servent
# uniquement à ne jamais ouvrir ni fermer une phrase d'accroche sur un mot vide
# ("de vieux souvenirs" -> "vieux souvenirs"). Aucune analyse grammaticale.
_FUNCTION_WORDS = frozenset(
    "le la les l un une des du de d au aux a en dans sur sous avec sans pour par vers chez "
    "et ou mais donc or ni car que qui quoi dont ce cet cette ces se me te lui y il elle ils elles "
    "je tu nous vous on mon ma mes ton ta tes son sa ses leur leurs ne n pas qu s j c m t jusqu lorsqu "
    "est etait sont etaient ete avait avaient ai as ont fait fasse "
    "the an of to in on at for with by from and or but so that which who whom it its is are was were "
    "be been being has have had this these those as then than if".split()
)
# Mots de liaison à retirer en tête de clause ("ou attendu le bon moment").
_LEADING_LINKS = frozenset("et ou mais donc alors puis and but or so then".split())
_ELISION = re.compile(r"^(?:[a-z]+)['’]")


def _plain(word: str) -> str:
    folded = unicodedata.normalize("NFKD", word.lower())
    return "".join(c for c in folded if not unicodedata.combining(c)).strip(".,;:!?…\"()[]«»")


def _is_function_word(word: str) -> bool:
    plain = _plain(word)
    if plain in _FUNCTION_WORDS:
        return True
    elided = _ELISION.match(plain)
    # "qu'elle", "n'avait", "jusqu'a" : mot vide si ce qui suit l'apostrophe l'est ;
    # "l'interieur" garde son nom.
    return bool(elided) and plain[elided.end():] in _FUNCTION_WORDS


def derive_emphasis_phrase(text: str, max_words: int = 4, min_words: int = 2) -> str | None:
    """A short ALL-CAPS phrase to hit hard on screen, taken from the END of the
    narration (where spoken stress falls): the last clause, trimmed to its last
    `max_words` words, never starting on a function word (it already ends where the clause ends).

    Deterministic, no LLM, nothing invented. Returns `None` when no phrase would add anything:
    fewer than `min_words` words remain, or the phrase is the WHOLE sentence (the
    captions already show it, so repeating it full-screen is a pure duplicate).
    Source is the narration only: `visual` is an image/camera direction, never
    viewer text."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", (text or "").strip()) if part.strip()]
    if not sentences:
        return None
    sentence = sentences[-1]
    whole = [w for w in sentence.split() if _plain(w)]
    clauses = [c.strip() for c in re.split(r"[,;:—–]|\s-\s", sentence) if c.strip()]
    words = [w for w in clauses[-1].split() if _plain(w)]
    while words and _plain(words[0]) in _LEADING_LINKS:
        words = words[1:]
    words = words[-max_words:]
    while words and _is_function_word(words[0]):
        words = words[1:]
    if len(words) < min_words or len(words) >= len(whole):
        return None
    phrase = " ".join(words).strip(" .,!?;:…\"()«»")
    return phrase.upper() or None


LEAD_SECONDS = 0.12   # le texte apparait juste avant le mot (comme motion_graphics/sync.py)
MAX_ANCHOR = 0.92     # ...mais toujours visible avant la fin du bloc


def _spoken_keys(words: list[dict]) -> list[tuple[str, float]]:
    keys = [(_plain(str(w.get("text") or "")), float(w.get("start") or 0.0)) for w in words if isinstance(w, dict)]
    return [(key, start) for key, start in keys if key]


def spoken_start(scene: dict, words: list[dict]) -> float | None:
    """Instant (s, depuis le debut du bloc) ou la voix commence a dire ce que la scene affiche, ou `None`.

    - nombre (`big_number`) : memes chiffres, jetons numeriques consecutifs concatenes (« 3 », « 000 » = 3000),
      premiere occurrence ;
    - phrase d'accroche (`icon_text`) : la suite exacte de mots, DERNIERE occurrence (la phrase vient de la
      fin de la narration : un mot repete plus tot ne doit pas l'avancer)."""
    keys = _spoken_keys(words)
    if scene.get("sceneType") == "big_number":
        digits = re.sub(r"\D", "", str(scene.get("displayValue") or ""))
        if not digits:
            return None
        nums = [(re.sub(r"\D", "", key), start) for key, start in keys]
        for i in range(len(nums)):
            acc = ""
            for j in range(i, min(i + 4, len(nums))):
                if not nums[j][0]:
                    break
                acc += nums[j][0]
                if acc == digits:
                    return nums[i][1]
                if len(acc) > len(digits):
                    break
        return None
    if scene.get("sceneType") == "icon_text":
        target = [_plain(w) for w in str(scene.get("text") or "").split() if _plain(w)]
        if not target:
            return None
        found = None
        for i in range(len(keys) - len(target) + 1):
            if [key for key, _ in keys[i:i + len(target)]] == target:
                found = keys[i][1]
        return found
    return None


def build_anchored_emphasis_scene(block: dict, words: list[dict] | None, duration: float) -> dict | None:
    """`build_emphasis_scene` + `_anchor` : la typographie apparait quand la voix la dit, pas au debut du bloc
    (une phrase tiree de la fin de la narration s'affichait 1 a 3 s avant d'etre prononcee).

    Une scene deja ecrite dans le script (`motion_graphic`) est rendue telle quelle. Sans mots (timestamps
    absents) ou sans correspondance sure : aucune ancre, comportement d'avant (apparition au debut du bloc)."""
    scene = build_emphasis_scene(block)
    if scene is None or scene is block.get("motion_graphic") or not words or duration <= 0:
        return scene
    start = spoken_start(scene, words)
    if start is None:
        return scene
    anchor = min(max(0.0, start - LEAD_SECONDS) / duration, MAX_ANCHOR)
    return {**scene, "_anchor": round(anchor, 4), "_duration": float(duration)}


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

    phrase = derive_emphasis_phrase(text)
    if phrase:
        return {"sceneType": "icon_text", "text": phrase}
    return None
