"""One render function per scene type — each takes the scene's (validated)
data, the local timeline progress `t` in [0, 1], the resolved theme and the
frame size, and returns a finished RGB frame.

Shared conventions:
- Text "fades in" via `theme.lerp_color` from the flat background color
  toward its target color (cheap, looks right against a solid backdrop,
  avoids per-glyph alpha compositing).
- Text "scales in" by animating the font size itself for the frame.
- Everything important stays inside `canvas.safe_box` (clear of the caption
  band and the top platform-UI band).
- No scene ever computes or invents a number: `value`/`displayValue` come
  straight from the validated scene data (see schema.py).
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from . import animations as anim
from . import canvas
from . import icons
from . import layout
from .theme import Theme, lerp_color


# Seconds an item takes to fade in once the narrator reaches it.
_REVEAL_FADE_SECONDS = 0.35


def _stag(data: dict, t: float, index: int, count: int, start: float = 0.05, span: float = 0.55, item_duration: float = 0.35) -> float:
    """Item entrance progress. When `engine.motion_graphics.sync` attached
    narration-derived reveal times (`_reveals`, normalised 0..1), the item
    appears when the narrator says it; otherwise the original even stagger."""
    reveals = data.get("_reveals")
    if reveals and index < len(reveals):
        duration = max(float(data.get("_duration") or 0.0), 0.5)
        r = float(reveals[index])
        return anim.ease_out_cubic(anim.phase(t, r, r + _REVEAL_FADE_SECONDS / duration))
    return anim.stagger(t, index, count, start, span, item_duration)


def _title(image: Image.Image, draw, theme: Theme, size: tuple[int, int], text: str, t: float, y_ratio: float = 0.15) -> None:
    """Phase 2.7 fix: width-fit via `layout.draw_fitted` — every scene calls
    this for its title, so this one change protects all of them from a
    long/translated title overflowing the frame edges."""
    if not text:
        return
    w, h = size
    base_px = round(h * 0.03)
    color = lerp_color(theme.background, theme.secondary, anim.fade_in(t, 0.0, 0.2))
    offset = anim.slide_up(t, 0.0, 0.25, distance=18)
    layout.draw_fitted(draw, (w / 2, h * y_ratio + offset), text.upper(), base_px, w * 0.88, color, bold=True)


def _label(image: Image.Image, draw, theme: Theme, size: tuple[int, int], text: str, t: float, y_ratio: float, start: float = 0.15) -> None:
    if not text:
        return
    w, h = size
    base_px = round(h * 0.026)
    color = lerp_color(theme.background, theme.muted_text, anim.fade_in(t, start, start + 0.2))
    layout.draw_fitted(draw, (w / 2, h * y_ratio), text.upper(), base_px, w * 0.88, color, bold=True)


def _big_value(image: Image.Image, draw, theme: Theme, size: tuple[int, int], data: dict, t: float, y_ratio: float = 0.42, color: str | None = None) -> None:
    """Draws `data['displayValue']`, animating a real count-up toward it when
    `data['value']` (a number) is present, and a scale/fade entrance either
    way. Phase 2.7 fix: width-fit — a long non-numeric displayValue no
    longer overflows the frame (numeric count-up values stay short, so this
    only ever engages for unexpectedly long text)."""
    w, h = size
    display = str(data.get("displayValue") or "")
    if not display:
        return
    target = data.get("value")
    text = display
    if isinstance(target, (int, float)) and not isinstance(target, bool):
        progress = anim.count_up(t, float(target), start=0.05, end=0.55)
        text = anim.format_like(display, progress)
    base_size = round(h * 0.11)
    scale = anim.scale_in(t, 0.0, 0.3, from_scale=0.8)
    base_px = max(1, round(base_size * scale))
    fill = lerp_color(theme.background, color or theme.text, anim.fade_in(t, 0.0, 0.2))
    layout.draw_fitted(draw, (w / 2, h * y_ratio), text, base_px, w * 0.9, fill, bold=True)


def _icon(image: Image.Image, draw, theme: Theme, size: tuple[int, int], name: str | None, t: float, y_ratio: float = 0.2, color: str | None = None) -> None:
    if not name:
        return
    w, h = size
    span = h * 0.09
    cx = w / 2
    cy = h * y_ratio
    scale = anim.scale_in(t, 0.0, 0.25, from_scale=0.6)
    half = (span * scale) / 2
    icons.draw_icon(draw, name, (cx - half, cy - half, cx + half, cy + half), color or theme.primary)


def render_big_number(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _icon(image, draw, theme, size, data.get("icon"), t, y_ratio=0.24)
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.36)
    _big_value(image, draw, theme, size, data, t, y_ratio=0.48)
    # Phase 2.7: was 0.58, exactly at the (now-tightened) caption-reserved
    # boundary — a couple of rows of margin against canvas.SAFE_BOTTOM_RATIO.
    _label(image, draw, theme, size, data.get("label") or "", t, y_ratio=0.55, start=0.35)
    return image


def render_money_split(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    top, _, bottom_limit = canvas.safe_box(w, h)[1], 0, canvas.safe_box(w, h)[3]
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    if data.get("displayValue"):
        _big_value(image, draw, theme, size, {"displayValue": data["displayValue"], "value": data.get("value")}, t, y_ratio=0.26)
        rows_start_ratio = 0.4
    else:
        rows_start_ratio = 0.3
    rows = data.get("data") or []
    # Density guard (Phase 2.7, section 7): drop the lowest-priority (last)
    # rows rather than render rows too short to stay legible.
    rows = rows[: layout.max_rows_for_height(bottom_limit - h * rows_start_ratio, len(rows))]
    n = len(rows)
    row_h = (bottom_limit - h * rows_start_ratio) / max(n, 1)
    emphasis = str(data.get("emphasis") or "").strip().lower()
    label_base_px = round(h * 0.028)
    value_base_px = round(h * 0.032)
    for i, row in enumerate(rows):
        p = _stag(data, t, i, n, start=0.1, span=0.6, item_duration=0.4)
        offset = anim.slide_up(t, 0, 1, distance=24) * (1 - p) if p < 1 else 0
        cy = h * rows_start_ratio + row_h * i + row_h / 2 + offset
        is_emphasis = str(row.get("label", "")).strip().lower() == emphasis
        accent = theme.accent if is_emphasis else theme.primary
        color = lerp_color(theme.background, accent, p)
        bar_x0 = w * 0.12
        bar_x1 = w * 0.88
        canvas.rounded_rect(draw, (bar_x0, cy - row_h * 0.22, bar_x1, cy + row_h * 0.22), row_h * 0.18, outline=color, width=max(2, round(h * 0.004)))
        label_color = lerp_color(theme.background, theme.text, p)
        # Label (left) and value (right) share one row — each is fit to ~44%
        # of the bar width so a long one can never grow into the other
        # (same collision family as the comparison-card bug).
        half_width = (bar_x1 - bar_x0) * 0.44
        # `max_height` = the pill's own visual height: a wrapped label that
        # still doesn't fit shrinks further instead of poking outside it
        # (found during the Phase 2.7 scene audit — see the contact sheet).
        pill_height = row_h * 0.44
        layout.draw_fitted(
            draw, (bar_x0 + w * 0.03, cy), str(row.get("label", "")).upper(), label_base_px, half_width,
            label_color, bold=is_emphasis, anchor="lm", max_height=pill_height,
        )
        value_text = str(row.get("displayValue") or row.get("value") or "")
        layout.draw_fitted(
            draw, (bar_x1 - w * 0.03, cy), value_text, value_base_px, half_width, color, bold=True, anchor="rm",
            max_height=pill_height,
        )
    return image


def render_progress_bar(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.36)
    display_color = lerp_color(theme.background, theme.text, anim.fade_in(t, 0.1, 0.3))
    display_base_px = round(h * 0.034)
    layout.draw_fitted(
        draw, (w / 2, h * 0.44), str(data.get("displayValue") or ""), display_base_px, w * 0.86, display_color, bold=True,
    )

    ratio = anim.progress_fill(t, float(data["targetRatio"]))
    track_x0, track_x1 = w * 0.12, w * 0.88
    # Phase 2.7 fix: the track (to 0.58h) plus the "%" text below it (at
    # 0.63h) together reached past the new caption-reserved boundary — both
    # nudged up, `pct_text` now safely inside the content zone.
    track_y0, track_y1 = h * 0.48, h * 0.53
    canvas.rounded_rect(draw, (track_x0, track_y0, track_x1, track_y1), (track_y1 - track_y0) / 2, fill=lerp_color(theme.background, theme.secondary, 0.35))
    fill_x1 = track_x0 + (track_x1 - track_x0) * ratio
    if fill_x1 > track_x0 + 2:
        canvas.rounded_rect(draw, (track_x0, track_y0, fill_x1, track_y1), (track_y1 - track_y0) / 2, fill=theme.primary)
    pct_text = f"{round(ratio * 100)}%"
    pct_color = lerp_color(theme.background, theme.muted_text, anim.fade_in(t, 0.5, 0.7))
    f_pct = canvas.font(round(h * 0.024))
    canvas.draw_text(draw, (w / 2, h * 0.565), pct_text, f_pct, pct_color, bold=True)
    return image


def render_bar_chart(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    rows = data.get("data") or []
    # Phase 2.7 fix: `bottom_ratio` used to be a hardcoded 0.78, entirely
    # independent of the shared caption-reserved zone (canvas.safe_box) —
    # rows could and did extend under where captions are burned in. Now
    # bounded by the actual content zone, and row count is density-guarded.
    _, _, _, content_bottom_px = layout.content_zone(w, h)
    top_ratio, bottom_ratio = 0.26, content_bottom_px / h
    rows = rows[: layout.max_rows_for_height((bottom_ratio - top_ratio) * h, len(rows))]
    n = len(rows)
    values = [float(r.get("value", 0)) for r in rows]
    max_value = float(data.get("maxValue") or max(values, default=1) or 1)
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    label_base_px = round(h * 0.026)
    value_base_px = round(h * 0.026)
    # La piste s'arrête avant `value_x` : la valeur reste dans un couloir fixe
    # à droite, jamais poussée hors cadre par une barre proche du maximum.
    track_x0, track_x1 = w * 0.34, w * 0.72
    value_x = w * 0.76
    label_max_width = track_x0 - w * 0.05 - w * 0.02
    value_max_width = w - value_x - w * 0.03
    for i, row in enumerate(rows):
        p = _stag(data, t, i, n, start=0.08, span=0.65, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        label_color = lerp_color(theme.background, theme.text, min(p * 2, 1))
        row_max_height = row_h * 0.85
        layout.draw_fitted(
            draw, (w * 0.05, cy), str(row.get("label", "")).upper(), label_base_px, label_max_width,
            label_color, bold=True, anchor="lm", max_height=row_max_height,
        )
        ratio = (values[i] / max_value) if max_value else 0
        bar_x1 = track_x0 + (track_x1 - track_x0) * ratio * p
        bar_color = lerp_color(theme.background, theme.primary, p)
        canvas.rounded_rect(draw, (track_x0, cy - row_h * 0.24, max(track_x0 + 2, bar_x1), cy + row_h * 0.24), row_h * 0.18, fill=bar_color)
        value_text = str(row.get("displayValue") or row.get("value") or "")
        layout.draw_fitted(
            draw, (value_x, cy), value_text, value_base_px, value_max_width, label_color, bold=True, anchor="lm",
            max_height=row_max_height,
        )
    return image


def render_donut_chart(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    rows = data.get("data") or []
    values = [max(float(r.get("value", 0)), 0) for r in rows]
    total = sum(values) or 1
    palette = [theme.primary, theme.accent, theme.positive, theme.secondary, theme.negative]
    # Phase 2.7 fix: legend used to start at a hardcoded 0.62h (already past
    # the tightened caption-reserved zone, see canvas.SAFE_BOTTOM_RATIO) — the
    # donut is nudged up slightly and the legend now starts right after it,
    # bounded by the real content zone.
    # Preflight finding: at r=0.24w / cy=0.34h the legend started at ~1008px of a
    # 1120px content zone, so the density guard silently dropped the 3rd
    # legend row and the 2nd intruded the caption zone. A slightly smaller
    # donut higher up leaves room for a full 3-5 row legend.
    cx, cy, r = w / 2, h * 0.30, w * 0.19
    overall = anim.ease_out_cubic(anim.phase(t, 0.05, 0.8))
    start_angle = -90.0
    for i, value in enumerate(values):
        sweep = 360.0 * (value / total) * overall
        color = palette[i % len(palette)]
        if sweep > 0.5:
            draw.pieslice((cx - r, cy - r, cx + r, cy + r), start_angle, start_angle + sweep, fill=color)
        start_angle += 360.0 * (value / total) * overall if overall >= 1 else sweep
    hole = r * 0.55
    draw.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=theme.background)

    _, _, _, content_bottom_px = layout.content_zone(w, h)
    legend_y = cy + r + h * 0.04
    row_span = h * 0.045
    available = content_bottom_px - legend_y
    # Density guard: every chart segment still shows in the pie by colour —
    # only the supporting text legend is dropped if there isn't room for all
    # of it (priority ladder, section 6: decorative/supporting text may
    # disappear before primary information becomes unreadable).
    rows = rows[: layout.max_rows_for_height(available, len(rows))] if available > 0 else []
    if rows:
        row_span = min(row_span, available / len(rows))
    legend_base_px = round(h * 0.026)
    legend_max_width = w * 0.68
    n = len(rows)
    for i, row in enumerate(rows):
        p = _stag(data, t, i, n, start=0.5, span=0.4, item_duration=0.3)
        color = lerp_color(theme.background, palette[i % len(palette)], p)
        swatch = h * 0.014
        y = legend_y + i * row_span
        draw.ellipse((w * 0.2, y - swatch, w * 0.2 + swatch * 2, y + swatch), fill=color)
        text_color = lerp_color(theme.background, theme.text, p)
        label = str(row.get("label", "")).upper()
        value_text = row.get("displayValue") or (f"{round(100 * row.get('value', 0) / total)}%")
        layout.draw_fitted(
            draw, (w * 0.26, y), f"{label}  {value_text}", legend_base_px, legend_max_width,
            text_color, bold=True, anchor="lm", max_height=row_span * 0.85,
        )
    return image


def _card(image: Image.Image, draw, box, theme: Theme, alpha_progress: float):
    color = theme.secondary
    return canvas.panel(image, box, (box[3] - box[1]) * 0.12, color, alpha=round(26 * alpha_progress))


def render_comparison(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    """`optionA`/`optionB`'s `label` and `displayValue` are free-form script
    text, not guaranteed to be short ("$2,400") — a real production script
    used full phrases ("Avoid audit risk" / "Chase refunds"), which at the
    old fixed font size overflowed each card and collided in the middle of
    the frame (Phase 2.7 root cause). Both are now fit to the card's own
    width via `layout.draw_fitted` (shrink-then-wrap), never drawn past
    `card_max_width`."""
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    option_a, option_b = data.get("optionA") or {}, data.get("optionB") or {}
    label_base_px = round(h * 0.028)
    value_base_px = round(h * 0.045)

    def _option(box, option, index, accent):
        p = _stag(data, t, index, 2, start=0.1, span=0.5, item_duration=0.4)
        img, dr = _card(image, draw, box, theme, p)
        color = lerp_color(theme.background, theme.text, p)
        cx = (box[0] + box[2]) / 2
        card_max_width = (box[2] - box[0]) * 0.86
        layout.draw_fitted(
            dr, (cx, box[1] + (box[3] - box[1]) * 0.28), str(option.get("label", "")).upper(),
            label_base_px, card_max_width, color, bold=True,
        )
        value_color = lerp_color(theme.background, accent, p)
        layout.draw_fitted(
            dr, (cx, box[1] + (box[3] - box[1]) * 0.62), str(option.get("displayValue") or ""),
            value_base_px, card_max_width, value_color, bold=True,
        )
        return img

    box_a = (w * 0.08, h * 0.24, w * 0.46, h * 0.62)
    box_b = (w * 0.54, h * 0.24, w * 0.92, h * 0.62)
    image = _option(box_a, option_a, 0, theme.primary)
    image = _option(box_b, option_b, 1, theme.accent)
    draw = ImageDraw.Draw(image)
    vs_color = lerp_color(theme.background, theme.muted_text, anim.fade_in(t, 0.3, 0.5))
    f_vs = canvas.font(round(h * 0.03))
    canvas.draw_text(draw, (w / 2, h * 0.43), "VS", f_vs, vs_color, bold=True)
    return image


def render_before_after(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    """Phase 2.7 fix: `y_after` (label 0.62h, value 0.69h) sat well past the
    caption-reserved zone even under the OLD 0.30 ratio — the whole layout
    is compressed upward to fit the real content zone, and both labels/
    values are now width-fit (same collision family as the comparison bug:
    `displayValue` is free-form script text, not guaranteed to be short)."""
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    before, after = data.get("before") or {}, data.get("after") or {}
    label_base_px = round(h * 0.028)
    value_base_px = round(h * 0.05)
    value_max_width = w * 0.86

    p_before = anim.fade_in(t, 0.05, 0.3)
    y_before = h * 0.26
    color_before = lerp_color(theme.background, theme.muted_text, p_before)
    layout.draw_fitted(draw, (w / 2, y_before), str(before.get("label", "")).upper(), label_base_px, value_max_width, color_before, bold=True)
    layout.draw_fitted(draw, (w / 2, y_before + h * 0.06), str(before.get("displayValue") or ""), value_base_px, value_max_width, color_before, bold=True)

    arrow_p = anim.fade_in(t, 0.35, 0.5)
    arrow_color = lerp_color(theme.background, theme.secondary, arrow_p)
    ay0, ay1 = h * 0.38, h * 0.44
    draw.line((w / 2, ay0, w / 2, ay1), fill=arrow_color, width=max(2, round(h * 0.004)))
    draw.polygon([(w / 2 - h * 0.012, ay1 - h * 0.012), (w / 2 + h * 0.012, ay1 - h * 0.012), (w / 2, ay1 + h * 0.006)], fill=arrow_color)

    p_after = anim.ease_out_cubic(anim.phase(t, 0.5, 0.85))
    scale = anim.scale_in(t, 0.5, 0.85, from_scale=0.8)
    y_after = h * 0.48
    color_after = lerp_color(theme.background, theme.positive, p_after)
    layout.draw_fitted(draw, (w / 2, y_after), str(after.get("label", "")).upper(), label_base_px, value_max_width, color_after, bold=True)
    after_value_base_px = max(1, round(h * 0.06 * scale))
    layout.draw_fitted(draw, (w / 2, y_after + h * 0.06), str(after.get("displayValue") or ""), after_value_base_px, value_max_width, color_after, bold=True)
    return image


def render_timeline(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.15)
    steps = data.get("steps") or []
    n = len(steps)
    y = h * 0.45
    # 0.20w/0.80w (was 0.12/0.88): end dots must be far enough from the frame
    # edge that a label as wide as 90% of the step spacing still fits inside
    # the margin without being shifted into its neighbour.
    x0, x1 = w * 0.20, w * 0.80
    line_progress = anim.ease_out_cubic(anim.phase(t, 0.1, 0.75))
    line_color = lerp_color(theme.background, theme.secondary, 1.0 if line_progress > 0 else 0.0)
    if n > 1:
        draw.line((x0, y, x0 + (x1 - x0) * line_progress, y), fill=line_color, width=max(2, round(h * 0.004)))
    label_base_px = round(h * 0.024)
    # Each step's label is fit to its own share of the step spacing (minus a
    # small gutter) so adjacent labels on a crowded timeline can't grow into
    # each other — same collision family as the comparison-card bug.
    step_spacing = (x1 - x0) / max(n - 1, 1) if n > 1 else x1 - x0
    label_max_width = max(step_spacing * 0.9, w * 0.12)
    # 3+ steps: alternate labels below/above the line. Same-side neighbours are
    # then TWO spacings apart, so each label gets ~2x the width and keeps a
    # legible font instead of shrinking to ~28px (preflight: below the floor).
    zigzag = n >= 3
    edge_margin = w * 0.03
    for i, step in enumerate(steps):
        p = _stag(data, t, i, n, start=0.05, span=0.7, item_duration=0.35)
        cx = x0 if n <= 1 else x0 + (x1 - x0) * i / (n - 1)
        r = h * 0.014 * anim.scale_in(t, 0, 1, from_scale=0.3) if p > 0 else 0
        dot_color = lerp_color(theme.background, theme.primary, p)
        if r > 0:
            draw.ellipse((cx - r, y - r, cx + r, y + r), fill=dot_color)
        label_color = lerp_color(theme.background, theme.text, p)
        label = str(step).upper()
        # The first/last dots sit at 0.12w / 0.88w, closer to the frame edge
        # than half of a full-spacing label — centring there clipped the label
        # ("UARTERLY PAYMENT MADE"). Keep the fitted box inside the frame margin.
        if zigzag:
            width = min(step_spacing * 2 * 0.9, 2 * (min(cx, w - cx) - edge_margin))
            width = max(width, w * 0.12)
            label_y = y + h * 0.05 if i % 2 == 0 else y - h * 0.05
        else:
            width, label_y = label_max_width, y + h * 0.05
        fit = layout.fit_text(draw, label, label_base_px, width, bold=True, wrap_first=True)
        label_cx = layout.clamp_center_x(cx, fit.line_width / 2, w, edge_margin)
        layout.draw_fitted(
            draw, (label_cx, label_y), label, label_base_px, width, label_color, bold=True, wrap_first=True,
        )
    return image


def render_compound_growth(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    rows = data.get("data") or []
    # Phase 2.7 fix: `bottom_ratio` used to be a hardcoded 0.85 — past both
    # the old and the new caption-reserved zone. Now bounded by the real
    # content zone, with a density guard on the row count.
    _, _, _, content_bottom_px = layout.content_zone(w, h)
    top_ratio, bottom_ratio = 0.28, content_bottom_px / h
    rows = rows[: layout.max_rows_for_height((bottom_ratio - top_ratio) * h, len(rows))]
    n = len(rows)
    step_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    value_max_width = w - w * 0.62 - w * 0.05
    for i, row in enumerate(rows):
        p = _stag(data, t, i, n, start=0.05, span=0.75, item_duration=0.45)
        cy = top_ratio * h + step_h * i + step_h / 2
        is_last = i == n - 1
        color = theme.accent if is_last else theme.primary
        text_color = lerp_color(theme.background, color, p)
        label_color = lerp_color(theme.background, theme.muted_text, p)
        base_size = round(h * (0.03 + 0.015 * (i / max(n - 1, 1))))
        f_label = canvas.font(round(h * 0.02))
        layout.draw_fitted(
            draw, (w * 0.62, cy), str(row.get("displayValue") or ""), base_size, value_max_width,
            text_color, bold=True, anchor="lm", max_height=step_h * 0.6,
        )
        canvas.draw_text(draw, (w * 0.62, cy + base_size * 0.75), str(row.get("label", "")).upper(), f_label, label_color, anchor="lm")
        if i > 0:
            arrow_color = lerp_color(theme.background, theme.secondary, p)
            prev_cy = top_ratio * h + step_h * (i - 1) + step_h / 2
            draw.line((w * 0.4, prev_cy + step_h * 0.18, w * 0.4, cy - step_h * 0.18), fill=arrow_color, width=max(2, round(h * 0.003)))
        r = h * 0.012 * (0.6 + 0.4 * (i / max(n - 1, 1)))
        draw.ellipse((w * 0.4 - r, cy - r, w * 0.4 + r, cy + r), fill=text_color)
    return image


def render_checklist(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    items = data.get("items") or []
    # Phase 2.7 fix: `bottom_ratio` used to be a hardcoded 0.85 — well past
    # both the old and the new caption-reserved zone. Now bounded by the
    # real content zone, with a density guard on the row count.
    _, _, _, content_bottom_px = layout.content_zone(w, h)
    top_ratio, bottom_ratio = 0.26, content_bottom_px / h
    items = items[: layout.max_rows_for_height((bottom_ratio - top_ratio) * h, len(items))]
    n = len(items)
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    item_base_px = round(h * 0.028)
    icon_span = h * 0.03
    item_max_width = w - (w * 0.12 + icon_span * 1.6) - w * 0.05
    for i, item in enumerate(items):
        p = _stag(data, t, i, n, start=0.05, span=0.75, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        offset = (1 - p) * h * 0.02
        check_color = lerp_color(theme.background, theme.positive, p)
        box = (w * 0.12, cy - icon_span / 2 + offset, w * 0.12 + icon_span, cy + icon_span / 2 + offset)
        icons.draw_icon(draw, "check", box, check_color)
        text_color = lerp_color(theme.background, theme.text, p)
        layout.draw_fitted(
            draw, (w * 0.12 + icon_span * 1.6, cy + offset), str(item), item_base_px, item_max_width,
            text_color, bold=True, anchor="lm", max_height=row_h * 0.85,
        )
    return image


def render_warning(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    # Phase 2.7 fix: the panel's bottom edge (0.62h) sat slightly inside the
    # new, tighter caption-reserved zone (canvas.SAFE_BOTTOM_RATIO) — trimmed
    # to end at the real content-zone boundary instead of a hardcoded ratio.
    _, _, _, content_bottom_px = layout.content_zone(w, h)
    panel_bottom = min(h * 0.62, content_bottom_px)
    panel_box = (w * 0.08, h * 0.28, w * 0.92, panel_bottom)
    image, draw = canvas.panel(image, panel_box, h * 0.03, theme.negative, alpha=round(30 * anim.fade_in(t, 0, 0.2)))
    pulse = anim.pulse(t, start=0.3, amplitude=0.06)
    icon_span = h * 0.07 * pulse
    cx = w / 2
    icon_cy = h * 0.38
    icons.draw_icon(draw, "warning", (cx - icon_span / 2, icon_cy - icon_span / 2, cx + icon_span / 2, icon_cy + icon_span / 2), lerp_color(theme.background, theme.negative, anim.fade_in(t, 0, 0.2)))
    title_base_px = round(h * 0.04)
    title_color = lerp_color(theme.background, theme.text, anim.fade_in(t, 0.1, 0.3))
    title_max_width = (panel_box[2] - panel_box[0]) * 0.86
    layout.draw_fitted(draw, (cx, h * 0.48), str(data.get("title") or "").upper(), title_base_px, title_max_width, title_color, bold=True)
    if data.get("label"):
        label_base_px = round(h * 0.025)
        label_color = lerp_color(theme.background, theme.secondary, anim.fade_in(t, 0.25, 0.45))
        layout.draw_fitted(draw, (cx, h * 0.55), str(data["label"]).upper(), label_base_px, title_max_width, label_color, bold=True)
    return image


def render_formula(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.16)
    terms = data.get("terms") or []
    # Phase 2.7 fix: `bottom_ratio` used to be a hardcoded 0.8 — past both
    # the old and the new caption-reserved zone. Now bounded by the real
    # content zone, with a density guard on the row count and each term
    # width-fit so a long term can't run off either edge.
    _, _, _, content_bottom_px = layout.content_zone(w, h)
    top_ratio, bottom_ratio = 0.3, content_bottom_px / h
    terms = terms[: layout.max_rows_for_height((bottom_ratio - top_ratio) * h, len(terms))]
    n = len(terms)
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    term_max_width = w * 0.86
    for i, term in enumerate(terms):
        p = _stag(data, t, i, n, start=0.1, span=0.7, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        offset = anim.slide_up(t, 0, 1, distance=20) * (1 - p) if p < 1 else 0
        is_result = str(term).strip().startswith("=")
        color = theme.accent if is_result else theme.text
        text_color = lerp_color(theme.background, color, p)
        base_size = round(h * (0.036 if is_result else 0.03))
        layout.draw_fitted(
            draw, (w / 2, cy + offset), str(term).upper(), base_size, term_max_width, text_color, bold=True,
            max_height=row_h * 0.85,
        )
    return image


def render_icon_text(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _icon(image, draw, theme, size, data.get("icon"), t, y_ratio=0.32)
    text = str(data.get("text") or "")
    f = canvas.font(round(h * 0.036))
    color = lerp_color(theme.background, theme.text, anim.fade_in(t, 0.1, 0.35))
    lines = canvas.wrap_text(draw, text.upper(), f, w * 0.82)
    line_h = h * 0.05
    start_y = h * 0.48 - line_h * (len(lines) - 1) / 2
    offset = anim.slide_up(t, 0.05, 0.35, distance=16)
    for i, line in enumerate(lines):
        canvas.draw_text(draw, (w / 2, start_y + line_h * i + offset), line, f, color, bold=True)
    if data.get("label"):
        # Phase 2.7 fix: with several wrapped `text` lines, this position
        # used to be able to drift past the caption-reserved zone — now
        # clamped to the real content-zone bottom.
        _, _, _, content_bottom_px = layout.content_zone(w, h)
        label_y_ratio = min(0.48 + line_h * len(lines) / h + 0.06, content_bottom_px / h - 0.04)
        _label(image, draw, theme, size, str(data["label"]), t, y_ratio=label_y_ratio, start=0.35)
    return image


RENDERERS = {
    "big_number": render_big_number,
    "money_split": render_money_split,
    "progress_bar": render_progress_bar,
    "bar_chart": render_bar_chart,
    "donut_chart": render_donut_chart,
    "comparison": render_comparison,
    "before_after": render_before_after,
    "timeline": render_timeline,
    "compound_growth": render_compound_growth,
    "checklist": render_checklist,
    "warning": render_warning,
    "formula": render_formula,
    "icon_text": render_icon_text,
}
