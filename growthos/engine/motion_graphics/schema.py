"""Structured scene contract for the `motion_graphics` visual style.

This is the JSON shape `growthos-web` (`ai-actions.ts`) must emit per block
when `visual_style` is `motion_graphics`, under `block["motion_graphic"]` —
the same spot `block["visual"]` already occupies for AI-image styles (see
`engine/visuals.py`'s docstring on text vs visual).

The renderer never invents numbers: every value shown on screen must come
from this data, itself sourced from the script. `validate_scene` only checks
STRUCTURE (right shape, non-empty) — it is deliberately not a strict
type-checker, so a scene that is merely incomplete still renders (missing
optional fields are just omitted), matching the pipeline's "never block the
whole render" philosophy used throughout `engine/visuals.py`.

Phase 2.8 — VIEWER-VISIBLE vs PRODUCTION fields (see `display_text.py`):
only title / label / displayText (alias `text`, icon_text) / displayValue /
emphasis / data[] / optionA·optionB·before·after / steps / items / terms are
ever drawn. `icon`, `icons` pick drawn glyphs. Everything else —
`animation` ({"type": "sequential_pop"}), `visual`, descriptions, notes — is
production metadata and is dropped before any renderer runs:

    {"sceneType": "icon_text", "displayText": "Small purchases add up",
     "icons": ["shopping_cart", "wallet"], "animation": {"type": "sequential_pop"}}

`icon_text.text` is still accepted (legacy scripts); `displayText` wins.
"""
from __future__ import annotations

SCENE_TYPES = (
    "big_number", "money_split", "progress_bar", "bar_chart", "donut_chart",
    "comparison", "before_after", "timeline", "compound_growth", "checklist",
    "warning", "formula", "equation_steps", "function_graph", "icon_text",
)

# Used by the renderer when the requested scene type is unknown or its data
# fails validation (engine/motion_graphics/renderer.py) — always renderable
# from a single piece of text, so it can wrap the block's own narration/visual
# text as a last resort.
FALLBACK_SCENE_TYPE = "icon_text"

# Fields required per scene type before it is considered renderable.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "big_number": ("displayValue",),
    "money_split": ("data",),
    "progress_bar": ("displayValue", "targetRatio"),
    "bar_chart": ("data",),
    "donut_chart": ("data",),
    "comparison": ("optionA", "optionB"),
    "before_after": ("before", "after"),
    "timeline": ("steps",),
    "compound_growth": ("data",),
    "checklist": ("items",),
    "warning": ("title",),
    "formula": ("terms",),
    "equation_steps": ("steps",),
    "function_graph": ("slope", "intercept"),
    "icon_text": ("displayText|text",),
}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_data_item(item: object) -> bool:
    return (
        isinstance(item, dict)
        and bool(str(item.get("label", "")).strip())
        and ("value" not in item or _is_number(item.get("value")))
    )


def _valid_labelled_group(value: object) -> bool:
    return isinstance(value, dict) and bool(str(value.get("label", "")).strip())


def _valid_string_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(str(v).strip() for v in value)


def validate_scene(raw: object) -> dict | None:
    """Returns `raw` unchanged if it is a structurally valid scene, else
    `None`. Callers must fall back to a safe default scene on `None` —
    never raise, never fabricate the missing data themselves."""
    if not isinstance(raw, dict):
        return None
    scene_type = str(raw.get("sceneType") or raw.get("type") or "").strip()
    if scene_type not in SCENE_TYPES:
        return None

    for field in _REQUIRED_FIELDS[scene_type]:
        if "|" in field:  # alias group: any one non-empty
            if not any(str(raw.get(alt) or "").strip() for alt in field.split("|")):
                return None
            continue
        value = raw.get(field)
        if field == "data":
            if not (isinstance(value, list) and value and all(_valid_data_item(v) for v in value)):
                return None
        elif field == "steps" and scene_type == "equation_steps":
            if not (isinstance(value, list) and 2 <= len(value) <= 4 and all(
                isinstance(step, dict) and isinstance(step.get("equation"), str)
                and 0 < len(step["equation"]) <= 80
                and ("explanation" not in step or isinstance(step["explanation"], str))
                and ("spoken" not in step or isinstance(step["spoken"], str))
                for step in value
            )):
                return None
        elif field in ("steps", "items", "terms"):
            if not _valid_string_list(value):
                return None
        elif field in ("optionA", "optionB", "before", "after"):
            if not _valid_labelled_group(value):
                return None
        elif field in ("slope", "intercept"):
            if not _is_number(value) or not -100 <= value <= 100:
                return None
        elif field == "targetRatio":
            if not _is_number(value):
                return None
        elif not str(value or "").strip():
            return None
    return raw


def normalized_scene_type(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    scene_type = str(raw.get("sceneType") or raw.get("type") or "").strip()
    return scene_type if scene_type in SCENE_TYPES else None
