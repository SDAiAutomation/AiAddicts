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

from . import layout
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
