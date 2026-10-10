"""Phase 2.8 — display-text contract: VIEWER-VISIBLE content vs PRODUCTION
metadata.

ROOT CAUSE THIS FIXES (traced on content item d019a38c, blocks 1 and 4): the
script generator wrote a direction into the viewer field of an `icon_text`
scene — `motion_graphic.text = "Feeling richer leads to small purchases.
Animation: icons pop in—coffee, phone, keys—one after another."` — and
`render_icon_text` drew `data["text"]` verbatim. Nothing separated "what the
viewer reads" from "how the scene should be animated".

The contract, enforced at ONE choke point (`viewer_scene`, applied to every
scene renderer in `scenes.RENDERERS`):

  VIEWER-VISIBLE  sceneType, title, label, displayText / text (icon_text),
                  displayValue, emphasis, data[].label/displayValue,
                  optionA/optionB/before/after.label/displayValue,
                  steps[], items[], terms[], icon, icons[], numeric values.
  PRODUCTION      animation, visual, description, notes, instructions...
                  — anything else. Dropped before any text-drawing function
                  can see it.

`viewer_scene` is a WHITELIST (unknown keys never reach a renderer), plus a
deterministic last-resort guard (`strip_directions`) for direction phrasing
that slipped INTO a viewer field, plus per-field length budgets so Motion
Graphics communicates visually and does not duplicate the narration captions.
No network, no LLM call.
"""
from __future__ import annotations

import re

# --- Field classes ------------------------------------------------------

# Top-level scalar text fields drawn on screen.
_TEXT_FIELDS = ("title", "label", "displayValue", "emphasis")
_NUMBER_FIELDS = ("value", "targetRatio", "maxValue", "slope", "intercept", "xMin", "xMax", "yMin", "yMax", "highlightX")
_LIST_FIELDS = ("steps", "items", "terms")
_GROUP_FIELDS = ("optionA", "optionB", "before", "after")
# Engine-internal, set by sync.attach_reveals — never script content.
_INTERNAL_FIELDS = ("_reveals", "_duration", "_anchor", "_solutionKind", "_plan", "_domainExclusions")
# Non affichés : repères vocaux et réglages de la scène equation_steps (math_steps.py).
_STEP_ANCHOR_FIELDS = ("spoken", "sidesSpoken", "resultSpoken")
_EQUATION_SCENE_FIELDS = ("verify", "verifySpoken", "rhythm")

# --- Display-text budgets (characters, words) ---------------------------
#
# Generous enough that every legitimate designed string passes untouched
# (real scripts peak at ~45 chars for a checklist item); tight enough that a
# narration sentence pasted into a field is cut down. `icon_text` is the
# strictest: it is the one scene that is "just text", so it is where a
# paragraph is most likely to appear above the captions.
BUDGETS: dict[str, tuple[int, int]] = {
    "display_text": (52, 9),    # icon_text main line (2 lines at the scene font)
    "title": (64, 10),
    "label": (48, 8),
    "display_value": (44, 8),
    "list_item": (64, 10),
    "datum_label": (40, 7),
}

# --- Instruction-leak guard ---------------------------------------------

# Label-style markers ("Animation: ...") — the colon is REQUIRED so that
# ordinary words ("show", "scene", "pan") in a legitimate sentence survive.
_LABELS = (
    r"animation|animate|animated|camera|transition|visual|visuals|scene|show|shot|"
    r"zoom|pan|fade|icons?|motion|sfx|b-?roll"
)
# A label at the START of a sentence ("Animation: icons pop...") or after a
# dash / semicolon inside one ("...purchases — Camera: close-up").
_LABEL_START = re.compile(rf"^\W*(?:{_LABELS})\s*:", re.IGNORECASE)
_LABEL_INLINE = re.compile(rf"(?:\s[—–-]\s|[;—–]\s*)(?:{_LABELS})\s*:", re.IGNORECASE)
# Bracketed direction: "(animation: ...)", "[camera pans left]".
_BRACKETED = re.compile(rf"[\(\[]\s*(?:{_LABELS})\b[^\)\]]*[\)\]]", re.IGNORECASE)
# Unlabelled direction SENTENCES. Only unambiguous verbs — "numbers rise"
# or "show me the money" are legitimate copy and must survive.
_DIRECTION_SENTENCE = re.compile(
    r"^\W*(?:the\s+)?(?:icons?|text|numbers?|bars?|arrows?|labels?|words?|chart|graphic|items?)\s+"
    r"(?:pop|pops|fade|fades|slide|slides|zoom|zooms|animate|animates|appear\s+(?:one|in|sequentially))\b"
    r"|^\W*camera\s+(?:pans?|zooms?|tracks?|cuts?)\b",
    re.IGNORECASE,
)
# Bare imperative camera/motion verbs. Also valid English copy ("Fade out the
# old habit"), so they only count when the sentence is stage-direction short.
_DIRECTION_IMPERATIVE = re.compile(
    r"^\W*(?:zoom\s+(?:in|out)|fade\s+(?:in|out)|pan\s+(?:left|right|across)"
    r"|animate\s+(?:the|each|every|icons?|text|numbers?|bars?))\b",
    re.IGNORECASE,
)
_IMPERATIVE_MAX_WORDS = 6
_ICONS_POP = re.compile(r"\bicons?\s+pop", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def _sentences(text: str) -> list[str]:
    return [p for p in _SENTENCE_SPLIT.split(text.strip()) if p.strip()]


def _is_direction_sentence(part: str) -> bool:
    return bool(
        _DIRECTION_SENTENCE.search(part) or _ICONS_POP.search(part)
        or (_DIRECTION_IMPERATIVE.search(part) and len(part.split()) <= _IMPERATIVE_MAX_WORDS)
    )


def _split_leak(text: str) -> tuple[str, bool]:
    """(clean_text, leaked). Directions trail the legitimate copy, so the
    text is cut at the first direction clause and everything after it goes."""
    s = _BRACKETED.sub(" ", " ".join(str(text or "").split()))
    leaked = s != " ".join(str(text or "").split())
    kept: list[str] = []
    for part in _sentences(s):
        if _LABEL_START.search(part):
            return " ".join(kept), True
        inline = _LABEL_INLINE.search(part)
        if inline:
            kept.append(part[: inline.start()])
            return " ".join(kept), True
        if _is_direction_sentence(part):
            leaked = True
            continue
        kept.append(part)
    return " ".join(kept), leaked


def has_direction_leak(text: object) -> bool:
    """True if `text` carries production-direction phrasing."""
    return _split_leak(str(text or ""))[1]


MINUS = "−"
# Spaced hyphen / en dash between two operands: "2000 - 300", "REVENU - EPARGNE".
_SPACED_MINUS = re.compile(r"(?<=\S) [-–] (?=\S)")
# A hyphen glued to what it negates, at the start or after an operator: "-5", "-$20", "-x".
_SIGN_MINUS = re.compile(r"(?:^|(?<=[\s(=<>≤≥≠+×÷*/]))-(?=[\d$€£.]|[a-z]\b)", re.IGNORECASE)
_RELATION = re.compile(r"[=≠<>≤≥≈]")
_BEFORE_OPERAND = re.compile(r"[\d)%]$|^[a-z]$", re.IGNORECASE)
_AFTER_OPERAND = re.compile(r"^[\d$€£(]|^[a-z]$", re.IGNORECASE)


def normalize_operators(text: str) -> str:
    """Typographic minus (U+2212) where a hyphen is arithmetic, and ONLY there.

    Arithmetic means: a spaced hyphen/en dash in a string that states a relation
    ("REVENU - EPARGNE = BUDGET") or sits between two numeric operands
    ("2000 - 300"); a hyphen glued to a number or variable at the start or after an
    operator ("-5 + 2 = -3"). Hyphens inside words ("aurais-tu"), ranges
    ("2000-3000") and prose dashes ("Wants - needs") are left alone."""
    if not text or ("-" not in text and "–" not in text):
        return text
    relational = bool(_RELATION.search(text))

    def spaced(match: re.Match) -> str:
        if relational:
            return f" {MINUS} "
        before = text[: match.start()].rsplit(" ", 1)[-1]
        after = text[match.end():].split(" ", 1)[0]
        return f" {MINUS} " if _BEFORE_OPERAND.search(before) and _AFTER_OPERAND.search(after) else match.group(0)

    out = _SPACED_MINUS.sub(spaced, text)
    if relational or re.match(r"^-[\d$€£]", out):
        out = _SIGN_MINUS.sub(MINUS, out)
    return out


def _strip_edges(text: str, operators: bool = False) -> str:
    """Trim stray punctuation left around a viewer string. A leading hyphen is
    kept when it is a sign glued to its operand ("-5") or, with `operators`
    (formula terms), a spaced minus ("- EPARGNE"); a bare list-bullet hyphen
    ("- Save first") is dropped as before."""
    text = text.strip(" \t—–:;,")
    if text.startswith("-"):
        glued = len(text) > 1 and not text[1].isspace()
        if not (glued or operators):
            text = text.lstrip("- ")
    return re.sub(r"\s+-+$", "", text).rstrip(" \t:;,")


def strip_directions(text: object, operators: bool = False) -> str:
    """Removes production-direction clauses from a viewer string. Last-resort
    guard: the contract is that directions never get here; this only catches
    legacy / model slips. Conservative by design: label markers need their
    colon, so ordinary words ("show", "scene", "pan") are never touched.
    Arithmetic operators survive (see `normalize_operators`); `operators=True`
    marks a field made of formula terms, where a leading spaced "-" is a minus."""
    clean, _ = _split_leak(str(text or ""))
    out = _strip_edges(" ".join(clean.split()), operators)
    if operators and out.startswith("- "):
        out = f"{MINUS} {out[2:]}"
    return normalize_operators(out)


# --- Budgets ------------------------------------------------------------

def _word_count(text: str) -> int:
    return len(text.split())


def fit_budget(text: str, kind: str) -> str:
    """`text` within the `kind` budget: unchanged if it fits, else its first
    sentence/clause if that fits, else a word-boundary cut with an ellipsis."""
    max_chars, max_words = BUDGETS[kind]
    text = " ".join(str(text or "").split())
    if len(text) <= max_chars and _word_count(text) <= max_words:
        return text
    for part in re.split(r"(?<=[.!?…:;])\s+|\s[—–]\s", text):
        part = part.strip(" .:;—–-")
        if 8 <= len(part) <= max_chars and _word_count(part) <= max_words:
            return part
    words = text.split()[:max_words]
    cut = " ".join(words)
    if len(cut) > max_chars:
        cut = cut[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:—–-.") + "…"


def _clean(text: object, kind: str, operators: bool = False) -> str:
    return fit_budget(strip_directions(text, operators), kind)


def display_text_of(scene: dict) -> str:
    """The `icon_text` viewer line: `displayText` if present, else the legacy
    `text` — cleaned and within budget."""
    raw = scene.get("displayText") if str(scene.get("displayText") or "").strip() else scene.get("text")
    out = _clean(raw, "display_text")
    # a designed line, not a sentence: no trailing full stop
    return out[:-1].rstrip() if out.endswith(".") and not out.endswith("..") else out


# --- The whitelist ------------------------------------------------------

def _clean_datum(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    if "label" in raw:
        out["label"] = _clean(raw.get("label"), "datum_label")
    if raw.get("displayValue") not in (None, ""):
        out["displayValue"] = _clean(raw.get("displayValue"), "display_value")
    if "value" in raw:
        out["value"] = raw["value"]
    return out


def viewer_scene(scene: object) -> dict:
    """A NEW scene dict holding only viewer-visible fields, directions stripped
    and budgets applied. Idempotent. Every renderer receives this — never the
    raw script object."""
    if not isinstance(scene, dict):
        return {}
    out: dict = {}
    kind = scene.get("sceneType") or scene.get("type")
    if kind:
        out["sceneType"] = kind
    for key in _TEXT_FIELDS:
        if key in scene and scene[key] is not None:
            budget = {"title": "title", "label": "label", "displayValue": "display_value"}.get(key)
            out[key] = _clean(scene[key], budget) if budget else strip_directions(scene[key])
    for key in _NUMBER_FIELDS + _INTERNAL_FIELDS:
        if key in scene:
            out[key] = scene[key]
    if "icon" in scene:
        out["icon"] = scene["icon"]
    if isinstance(scene.get("icons"), list):
        out["icons"] = [i for i in scene["icons"] if isinstance(i, str)]
    if kind == "icon_text" or "text" in scene or "displayText" in scene:
        out["text"] = display_text_of(scene)
    if kind == "equation_steps" and isinstance(scene.get("steps"), list):
        out["steps"] = [
            {"equation": str(step["equation"]).strip(),
             "explanation": _clean(step.get("explanation", ""), "label"),
             **{key: step[key] for key in _STEP_ANCHOR_FIELDS if isinstance(step.get(key), str)}}
            for step in scene["steps"] if isinstance(step, dict) and isinstance(step.get("equation"), str)
        ]
        out.update({key: scene[key] for key in _EQUATION_SCENE_FIELDS if key in scene})
    for key in _LIST_FIELDS:
        if kind == "equation_steps" and key == "steps":
            continue
        if isinstance(scene.get(key), list):
            out[key] = [v for v in (_clean(v, "list_item", operators=key == "terms") for v in scene[key]) if v]
    if isinstance(scene.get("data"), list):
        out["data"] = [d for d in (_clean_datum(r) for r in scene["data"]) if d is not None]
    for key in _GROUP_FIELDS:
        datum = _clean_datum(scene.get(key))
        if datum is not None:
            out[key] = datum
    return out


def leaks_in_scene(scene: object) -> list[str]:
    """Raw viewer-field strings that carry a direction — for the audit and
    the render report, never for rendering."""
    found: list[str] = []
    if not isinstance(scene, dict):
        return found

    def check(value: object) -> None:
        if isinstance(value, str) and has_direction_leak(value):
            found.append(value)

    for key in _TEXT_FIELDS + ("text", "displayText"):
        check(scene.get(key))
    for key in _LIST_FIELDS:
        for v in scene.get(key) or []:
            if isinstance(v, dict):
                check(v.get("equation")), check(v.get("explanation"))
            else:
                check(v)
    for row in scene.get("data") or []:
        if isinstance(row, dict):
            check(row.get("label")), check(row.get("displayValue"))
    for key in _GROUP_FIELDS:
        row = scene.get(key)
        if isinstance(row, dict):
            check(row.get("label")), check(row.get("displayValue"))
    return found


_MATH_TOKEN = re.compile(r"[a-z][\u00b2\u00b3^0-9]*[.,:;!?]?")
_MATH_SYMBOLS = set("=\u2260<>\u2264\u2265+\u2212\u00d7\u00f7^\u00b2\u00b3/()0123456789")


def display_title(title: str) -> str:
    """Titre en majuscules SAUF les variables et les expressions mathématiques : « Isoler x » devient
    « ISOLER x », « x ≠ 1 » reste « x ≠ 1 » (mettre la variable en capitale en ferait un autre objet)."""
    out = []
    for token in str(title or "").split(" "):
        keep = _MATH_TOKEN.fullmatch(token) is not None or any(char in _MATH_SYMBOLS for char in token)
        out.append(token if keep else token.upper())
    return " ".join(out)
