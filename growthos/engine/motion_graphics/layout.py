"""Phase 2.7 — shared vertical safe-zone contract + deterministic text-fit /
collision helpers for every Motion Graphics scene.

ROOT CAUSE THIS FIXES (see the Phase 2.7 report for the full trace): a real
production video's `comparison` scene drew `optionA`/`optionB`'s
`displayValue` at a fixed large font size with NO width constraint —
`render_comparison` was implicitly written assuming a short numeric value
("$2,400"), but the script supplied a long phrase ("Avoid audit risk" /
"Chase refunds"). Each value overflowed its own card and the two overflowed
into each other in the middle of the frame. This module gives every scene a
small, deterministic way to measure text FIRST and shrink/wrap it to the
column it actually has, instead of assuming it will always be short — zero
AI calls, zero new providers, pure Pillow measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import canvas

# --- Canonical vertical safe-zone contract (9:16, ratio of HEIGHT) --------
#
# Single source of truth: engine/motion_graphics/canvas.py's
# SAFE_TOP_RATIO / SAFE_BOTTOM_RATIO (see that module for the full derivation
# of SAFE_BOTTOM_RATIO from engine/captions.py's real caption constants).
# Named here for readability at call sites that care about "the caption
# zone" rather than "the bottom safe ratio."
TOP_SAFE_RATIO = canvas.SAFE_TOP_RATIO
CAPTION_RESERVED_RATIO = canvas.SAFE_BOTTOM_RATIO
CONTENT_ZONE_TOP_RATIO = TOP_SAFE_RATIO
CONTENT_ZONE_BOTTOM_RATIO = 1 - CAPTION_RESERVED_RATIO


def content_zone(width: int, height: int) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the region clear of both the top platform-UI band
    and the bottom caption-reserved band — the only region designed text
    (Motion Graphics, kinetic typography, comic/game-art overlays) should
    put anything that matters into."""
    return 0, round(height * CONTENT_ZONE_TOP_RATIO), width, round(height * CONTENT_ZONE_BOTTOM_RATIO)


def caption_reserved_zone(width: int, height: int) -> tuple[int, int, int, int]:
    return 0, round(height * CONTENT_ZONE_BOTTOM_RATIO), width, height


def platform_safe_zone(width: int, height: int) -> tuple[int, int, int, int]:
    return 0, 0, width, round(height * TOP_SAFE_RATIO)


# --- Bounding-box measurement + collision detection -----------------------

def boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def intrudes_zone(box: tuple[float, float, float, float], zone: tuple[float, float, float, float]) -> bool:
    return boxes_overlap(box, zone)


def find_collisions(boxes: dict[str, tuple[float, float, float, float]]) -> list[tuple[str, str]]:
    """Every pair of ids whose boxes overlap — deterministic (dict insertion
    order), used by both the debug overlay and the regression test."""
    ids = list(boxes)
    pairs = []
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1:]:
            if boxes_overlap(boxes[id_a], boxes[id_b]):
                pairs.append((id_a, id_b))
    return pairs


# --- Deterministic text fitting (the actual fix for the reported bug) ----

# A scene's font never shrinks past this fraction of its requested size —
# below that, text wraps to another line instead of shrinking further. Once
# wrapped, a SECOND, lower floor applies if the wrapped block still doesn't
# fit a caller-supplied `max_height` (a fixed-height row, a card, a pill) —
# see `fit_text`'s `max_height` argument.
_MIN_FONT_RATIO = 0.6
_MIN_FONT_RATIO_WRAPPED = 0.45
_FONT_SHRINK_STEP = 0.9
_MAX_LINES = 3
_LINE_GAP = 1.22


@dataclass
class FitResult:
    font: object
    lines: list[str]
    line_width: float
    total_height: float


def fit_text(
    draw, text: str, base_font_px: int, max_width: float, *, bold: bool = False, max_height: float | None = None,
) -> FitResult:
    """The largest font size (down to `_MIN_FONT_RATIO` of `base_font_px`) at
    which `text` fits `max_width` on one line. If even the minimum size still
    doesn't fit on one line, wraps to up to `_MAX_LINES` lines at that
    minimum size instead — and if `max_height` is given and the wrapped
    block still doesn't fit it (e.g. a 2-line label inside a fixed-height
    row/pill), shrinks further down to `_MIN_FONT_RATIO_WRAPPED` before
    accepting the overflow. Never silently lets text overflow `max_width` —
    this is the direct, general fix for the reported comparison-card bug."""
    text = (text or "").strip()
    if not text:
        return FitResult(canvas.font(max(1, base_font_px)), [], 0.0, 0.0)
    min_px = max(1, round(base_font_px * _MIN_FONT_RATIO))
    stroke = max(1, base_font_px // 22) if bold else 0
    size = base_font_px
    while size > min_px:
        f = canvas.font(size)
        w, _h = canvas.text_size(draw, text, f, stroke_width=stroke)
        if w <= max_width:
            line_h = canvas.text_size(draw, "Ag", f, stroke_width=stroke)[1]
            return FitResult(f, [text], w, line_h)
        size = max(min_px, round(size * _FONT_SHRINK_STEP))

    wrap_min_px = max(1, round(base_font_px * _MIN_FONT_RATIO_WRAPPED))
    size = min_px
    while True:
        f = canvas.font(size)
        lines = canvas.wrap_text(draw, text, f, max_width)[:_MAX_LINES]
        line_h = canvas.text_size(draw, "Ag", f, stroke_width=stroke)[1]
        total_h = line_h * len(lines) * _LINE_GAP
        line_w = max((canvas.text_size(draw, line, f, stroke_width=stroke)[0] for line in lines), default=0)
        if max_height is None or total_h <= max_height or size <= wrap_min_px:
            return FitResult(f, lines, line_w, total_h)
        size = max(wrap_min_px, round(size * _FONT_SHRINK_STEP))


def draw_fitted(
    draw, xy: tuple[float, float], text: str, base_font_px: int, max_width: float, fill, *,
    bold: bool = False, anchor: str = "mm", max_height: float | None = None,
) -> tuple[int, int, int, int]:
    """Drop-in, width-safe replacement for `canvas.draw_text` wherever a
    value's length isn't guaranteed short (labels, displayValues, legend
    text, checklist items, formula terms...). Pass `max_height` for a
    fixed-height row/pill/card so a 2-line wrap doesn't just trade a
    horizontal overflow for a vertical one. Returns the bounding box it
    actually drew, for collision checks / the debug overlay."""
    result = fit_text(draw, text, base_font_px, max_width, bold=bold, max_height=max_height)
    x, y = xy
    if not result.lines:
        return (round(x), round(y), round(x), round(y))
    stroke = max(1, base_font_px // 22) if bold else 0
    line_h = canvas.text_size(draw, "Ag", result.font, stroke_width=stroke)[1] * _LINE_GAP
    vertical_center = "m" == anchor[1:2] if len(anchor) > 1 else False
    start_y = y - (len(result.lines) - 1) * line_h / 2 if vertical_center else y
    boxes = []
    for i, line in enumerate(result.lines):
        ly = start_y + i * line_h
        canvas.draw_text(draw, (x, ly), line, result.font, fill, anchor=anchor, bold=bold)
        boxes.append(draw.textbbox((x, ly), canvas.sanitize_text(line), font=result.font, anchor=anchor, stroke_width=stroke))
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return (round(x0), round(y0), round(x1), round(y1))


def clamp_center_x(cx: float, half_width: float, frame_width: int, margin: float) -> float:
    """Shifts a horizontally-centred box's centre so the whole box stays inside
    [margin, frame_width - margin]. Used for labels centred on a point that
    sits near a frame edge (first/last timeline step) — a label as wide as its
    step spacing is wider than the distance from that point to the edge, so
    centring it there clips it against the frame."""
    lo = margin + half_width
    hi = frame_width - margin - half_width
    if lo > hi:
        return frame_width / 2
    return min(max(cx, lo), hi)


# --- Density guard (section 7) --------------------------------------------

# Below this row height (px, on a 1920-tall reference canvas), a row of text
# is no longer comfortably legible on a phone screen — matches the smallest
# body font used anywhere in scenes.py (h*0.02 ≈ 38px on 1920) plus margin.
_MIN_ROW_HEIGHT_PX = 46


def max_rows_for_height(available_height_px: float, requested_rows: int) -> int:
    """Deterministic density guard: if `requested_rows` evenly dividing
    `available_height_px` would fall below the legible row-height floor,
    caps the count instead of silently rendering unreadable rows. Callers
    drop the LOWEST-PRIORITY rows first (schema order = priority order for
    every row-based scene: checklist/timeline/formula list items front-to-
    back, money_split/bar_chart/donut_chart rows in the order the script
    gave them)."""
    if requested_rows <= 0:
        return 0
    row_h = available_height_px / requested_rows
    if row_h >= _MIN_ROW_HEIGHT_PX:
        return requested_rows
    return max(1, int(available_height_px // _MIN_ROW_HEIGHT_PX))


# --- Debug layout mode (section 10) ---------------------------------------

@dataclass
class DebugCollector:
    """Optional per-frame collector a scene can append its drawn text boxes
    to. `None` everywhere in production — see engine/motion_graphics/
    renderer.py, gated behind the MOTION_GRAPHICS_DEBUG_LAYOUT env flag."""
    boxes: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)

    def add(self, box_id: str, box: tuple[float, float, float, float]) -> None:
        self.boxes[box_id] = box


def draw_debug_overlay(image, debug: "DebugCollector | None" = None):
    """Draws the safe-zone guides (and any collected text boxes / detected
    collisions) directly onto `image` — LOCAL/DEBUG-only, never called
    unless MOTION_GRAPHICS_DEBUG_LAYOUT is set (see renderer.py)."""
    from PIL import ImageDraw

    w, h = image.size
    draw = ImageDraw.Draw(image)
    draw.rectangle(platform_safe_zone(w, h), outline=(255, 0, 255), width=2)
    draw.rectangle(content_zone(w, h), outline=(0, 200, 0), width=2)
    draw.rectangle(caption_reserved_zone(w, h), outline=(255, 140, 0), width=2)
    if debug and debug.boxes:
        collisions = {id_ for pair in find_collisions(debug.boxes) for id_ in pair}
        for box_id, box in debug.boxes.items():
            color = (255, 0, 0) if box_id in collisions else (0, 160, 255)
            draw.rectangle(box, outline=color, width=2)
    return image
