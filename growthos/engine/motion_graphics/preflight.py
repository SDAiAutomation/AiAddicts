"""Layout preflight for Motion Graphics scenes.

Renders a scene's SETTLED frame (t = 1.0, every item visible) with the
`layout.record_boxes` recorder on, then checks the recorded text boxes:

  errors (the scene is swapped for the safe fallback):
    - two text boxes overlap            ("overlap")
    - a text box leaves the frame margin ("out_of_frame")
    - a text box enters the caption zone ("caption_zone")
  warnings (reported, not acted on):
    - a font smaller than the legibility floor ("small_text")

Pure Pillow, no network, ~one frame per scene. The Phase 2.7 bug (labels
overlapping and clipping in a timeline) reached production because nothing
looked at the result; this is that missing look.
"""
from __future__ import annotations

from . import display_text, layout
from .scenes import RENDERERS
from .theme import Theme

_EDGE_MARGIN_RATIO = 0.02  # of width
_OVERLAP_TOLERANCE_PX = 2
# Smallest comfortable font on the 1080x1920 reference canvas (~11 pt on a
# 390 pt-wide phone). Scaled by the real frame height.
MIN_FONT_PX_1920 = 30


def check_scene(scene: dict, theme: Theme, size: tuple[int, int]) -> dict:
    w, h = size
    kind = scene.get("sceneType") or "icon_text"
    render = RENDERERS.get(kind, RENDERERS["icon_text"])
    with layout.record_boxes() as recorded:
        render(scene, 1.0, theme, size)

    zone = layout.caption_reserved_zone(w, h)
    margin = w * _EDGE_MARGIN_RATIO
    min_font = MIN_FONT_PX_1920 * h / 1920
    errors: list[dict] = []
    warnings: list[dict] = []

    for i, a in enumerate(recorded):
        x0, y0, x1, y1 = a["box"]
        if x0 < margin or x1 > w - margin or y0 < 0:
            errors.append({"kind": "out_of_frame", "text": a["text"], "box": a["box"]})
        if layout.intrudes_zone(a["box"], zone):
            errors.append({"kind": "caption_zone", "text": a["text"], "box": a["box"]})
        if a["font"] < min_font:
            warnings.append({"kind": "small_text", "text": a["text"], "font": a["font"]})
        for b in recorded[i + 1:]:
            shrunk = (b["box"][0] + _OVERLAP_TOLERANCE_PX, b["box"][1] + _OVERLAP_TOLERANCE_PX,
                      b["box"][2] - _OVERLAP_TOLERANCE_PX, b["box"][3] - _OVERLAP_TOLERANCE_PX)
            if layout.boxes_overlap(a["box"], shrunk):
                errors.append({"kind": "overlap", "text": f'{a["text"]} / {b["text"]}', "box": a["box"]})

    return {
        "sceneType": kind,
        "textBoxes": len(recorded),
        "minFontPx": min((r["font"] for r in recorded), default=None),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


_FALLBACK_MAX_CHARS = 90


def _shorten(text: str, limit: int = _FALLBACK_MAX_CHARS) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…"


def fallback_text(scene: object, narration: str) -> str:
    """On-screen text for the `icon_text` fallback.

    Built from the failed scene's OWN content (its text, title, values, items...)
    and, only if there is none, from the narration. NEVER from the block's
    `visual`: that field is a shot description written for the editor
    ("Close_up, hands dropping $50 bills into a jar...") and must not be shown
    to viewers, nor from production metadata (`animation`, ...).
    """
    if isinstance(scene, dict):
        # viewer fields only, directions stripped (Phase 2.8): a leaked
        # "Animation: ..." in the failed scene must not resurface here.
        scene = display_text.viewer_scene(scene)
        pieces: list[str] = []
        for key in ("text", "title", "displayValue", "label"):
            if scene.get(key):
                pieces.append(str(scene[key]))
        for key in ("steps", "items", "terms"):
            values = scene.get(key)
            if isinstance(values, list) and values:
                pieces.append(" · ".join(str(v) for v in values))
        rows = scene.get("data")
        if isinstance(rows, list) and rows:
            pieces.append(" · ".join(
                f"{r.get('label', '')} {r.get('displayValue', '')}".strip() for r in rows if isinstance(r, dict)))
        for key in ("optionA", "optionB", "before", "after"):
            opt = scene.get(key)
            if isinstance(opt, dict) and (opt.get("label") or opt.get("displayValue")):
                pieces.append(f"{opt.get('label', '')} {opt.get('displayValue', '')}".strip())
        if pieces:
            # title first when there is one, then the content
            return _shorten(" — ".join(p for p in pieces if p)[:400])
    sentence = " ".join(str(narration or "").split())
    for sep in (". ", "? ", "! "):
        if sep in sentence:
            sentence = sentence.split(sep, 1)[0]
            break
    return _shorten(sentence) or " "
