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
from .theme import Theme, lerp_color


def _title(image: Image.Image, draw, theme: Theme, size: tuple[int, int], text: str, t: float, y_ratio: float = 0.15) -> None:
    if not text:
        return
    w, h = size
    f = canvas.font(round(h * 0.03))
    color = lerp_color(theme.background, theme.secondary, anim.fade_in(t, 0.0, 0.2))
    offset = anim.slide_up(t, 0.0, 0.25, distance=18)
    canvas.draw_text(draw, (w / 2, h * y_ratio + offset), text.upper(), f, color, bold=True)


def _label(image: Image.Image, draw, theme: Theme, size: tuple[int, int], text: str, t: float, y_ratio: float, start: float = 0.15) -> None:
    if not text:
        return
    w, h = size
    f = canvas.font(round(h * 0.026))
    color = lerp_color(theme.background, theme.muted_text, anim.fade_in(t, start, start + 0.2))
    canvas.draw_text(draw, (w / 2, h * y_ratio), text.upper(), f, color, bold=True)


def _big_value(image: Image.Image, draw, theme: Theme, size: tuple[int, int], data: dict, t: float, y_ratio: float = 0.42, color: str | None = None) -> None:
    """Draws `data['displayValue']`, animating a real count-up toward it when
    `data['value']` (a number) is present, and a scale/fade entrance either
    way."""
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
    f = canvas.font(max(1, round(base_size * scale)))
    fill = lerp_color(theme.background, color or theme.text, anim.fade_in(t, 0.0, 0.2))
    canvas.draw_text(draw, (w / 2, h * y_ratio), text, f, fill, bold=True)


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
    _label(image, draw, theme, size, data.get("label") or "", t, y_ratio=0.58, start=0.35)
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
    n = len(rows)
    row_h = (bottom_limit - h * rows_start_ratio) / max(n, 1)
    emphasis = str(data.get("emphasis") or "").strip().lower()
    f_label = canvas.font(round(h * 0.028))
    f_value = canvas.font(round(h * 0.032))
    for i, row in enumerate(rows):
        p = anim.stagger(t, i, n, start=0.1, span=0.6, item_duration=0.4)
        offset = anim.slide_up(t, 0, 1, distance=24) * (1 - p) if p < 1 else 0
        cy = h * rows_start_ratio + row_h * i + row_h / 2 + offset
        is_emphasis = str(row.get("label", "")).strip().lower() == emphasis
        accent = theme.accent if is_emphasis else theme.primary
        color = lerp_color(theme.background, accent, p)
        bar_x0 = w * 0.12
        bar_x1 = w * 0.88
        canvas.rounded_rect(draw, (bar_x0, cy - row_h * 0.22, bar_x1, cy + row_h * 0.22), row_h * 0.18, outline=color, width=max(2, round(h * 0.004)))
        label_color = lerp_color(theme.background, theme.text, p)
        canvas.draw_text(draw, (bar_x0 + w * 0.03, cy), str(row.get("label", "")).upper(), f_label, label_color, anchor="lm", bold=is_emphasis)
        value_text = str(row.get("displayValue") or row.get("value") or "")
        canvas.draw_text(draw, (bar_x1 - w * 0.03, cy), value_text, f_value, color, anchor="rm", bold=True)
    return image


def render_progress_bar(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.36)
    display_color = lerp_color(theme.background, theme.text, anim.fade_in(t, 0.1, 0.3))
    f = canvas.font(round(h * 0.034))
    canvas.draw_text(draw, (w / 2, h * 0.45), str(data.get("displayValue") or ""), f, display_color, bold=True)

    ratio = anim.progress_fill(t, float(data["targetRatio"]))
    track_x0, track_x1 = w * 0.12, w * 0.88
    track_y0, track_y1 = h * 0.52, h * 0.58
    canvas.rounded_rect(draw, (track_x0, track_y0, track_x1, track_y1), (track_y1 - track_y0) / 2, fill=lerp_color(theme.background, theme.secondary, 0.35))
    fill_x1 = track_x0 + (track_x1 - track_x0) * ratio
    if fill_x1 > track_x0 + 2:
        canvas.rounded_rect(draw, (track_x0, track_y0, fill_x1, track_y1), (track_y1 - track_y0) / 2, fill=theme.primary)
    pct_text = f"{round(ratio * 100)}%"
    pct_color = lerp_color(theme.background, theme.muted_text, anim.fade_in(t, 0.5, 0.7))
    f_pct = canvas.font(round(h * 0.024))
    canvas.draw_text(draw, (w / 2, h * 0.63), pct_text, f_pct, pct_color, bold=True)
    return image


def render_bar_chart(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    rows = data.get("data") or []
    n = len(rows)
    values = [float(r.get("value", 0)) for r in rows]
    max_value = float(data.get("maxValue") or max(values, default=1) or 1)
    top_ratio, bottom_ratio = 0.26, 0.78
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    f_label = canvas.font(round(h * 0.026))
    f_value = canvas.font(round(h * 0.026))
    # La piste s'arrête avant `value_x` : la valeur reste dans un couloir fixe
    # à droite, jamais poussée hors cadre par une barre proche du maximum.
    track_x0, track_x1 = w * 0.34, w * 0.72
    value_x = w * 0.76
    for i, row in enumerate(rows):
        p = anim.stagger(t, i, n, start=0.08, span=0.65, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        label_color = lerp_color(theme.background, theme.text, min(p * 2, 1))
        canvas.draw_text(draw, (w * 0.05, cy), str(row.get("label", "")).upper(), f_label, label_color, anchor="lm", bold=True)
        ratio = (values[i] / max_value) if max_value else 0
        bar_x1 = track_x0 + (track_x1 - track_x0) * ratio * p
        bar_color = lerp_color(theme.background, theme.primary, p)
        canvas.rounded_rect(draw, (track_x0, cy - row_h * 0.24, max(track_x0 + 2, bar_x1), cy + row_h * 0.24), row_h * 0.18, fill=bar_color)
        value_text = str(row.get("displayValue") or row.get("value") or "")
        canvas.draw_text(draw, (value_x, cy), value_text, f_value, label_color, anchor="lm", bold=True)
    return image


def render_donut_chart(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    rows = data.get("data") or []
    values = [max(float(r.get("value", 0)), 0) for r in rows]
    total = sum(values) or 1
    palette = [theme.primary, theme.accent, theme.positive, theme.secondary, theme.negative]
    cx, cy, r = w / 2, h * 0.38, w * 0.28
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

    legend_y = h * 0.62
    f_legend = canvas.font(round(h * 0.026))
    n = len(rows)
    for i, row in enumerate(rows):
        p = anim.stagger(t, i, n, start=0.5, span=0.4, item_duration=0.3)
        color = lerp_color(theme.background, palette[i % len(palette)], p)
        swatch = h * 0.014
        y = legend_y + i * h * 0.045
        draw.ellipse((w * 0.2, y - swatch, w * 0.2 + swatch * 2, y + swatch), fill=color)
        text_color = lerp_color(theme.background, theme.text, p)
        label = str(row.get("label", "")).upper()
        value_text = row.get("displayValue") or (f"{round(100 * row.get('value', 0) / total)}%")
        canvas.draw_text(draw, (w * 0.26, y), f"{label}  {value_text}", f_legend, text_color, anchor="lm", bold=True)
    return image


def _card(image: Image.Image, draw, box, theme: Theme, alpha_progress: float):
    color = theme.secondary
    return canvas.panel(image, box, (box[3] - box[1]) * 0.12, color, alpha=round(26 * alpha_progress))


def render_comparison(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    option_a, option_b = data.get("optionA") or {}, data.get("optionB") or {}
    f_label = canvas.font(round(h * 0.028))
    f_value = canvas.font(round(h * 0.045))

    def _option(box, option, index, accent):
        p = anim.stagger(t, index, 2, start=0.1, span=0.5, item_duration=0.4)
        img, dr = _card(image, draw, box, theme, p)
        color = lerp_color(theme.background, theme.text, p)
        cx = (box[0] + box[2]) / 2
        canvas.draw_text(dr, (cx, box[1] + (box[3] - box[1]) * 0.28), str(option.get("label", "")).upper(), f_label, color, bold=True)
        value_color = lerp_color(theme.background, accent, p)
        canvas.draw_text(dr, (cx, box[1] + (box[3] - box[1]) * 0.62), str(option.get("displayValue") or ""), f_value, value_color, bold=True)
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
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.13)
    before, after = data.get("before") or {}, data.get("after") or {}
    f_label = canvas.font(round(h * 0.028))
    f_value = canvas.font(round(h * 0.05))

    p_before = anim.fade_in(t, 0.05, 0.3)
    y_before = h * 0.32
    color_before = lerp_color(theme.background, theme.muted_text, p_before)
    canvas.draw_text(draw, (w / 2, y_before), str(before.get("label", "")).upper(), f_label, color_before, bold=True)
    canvas.draw_text(draw, (w / 2, y_before + h * 0.06), str(before.get("displayValue") or ""), f_value, color_before, bold=True)

    arrow_p = anim.fade_in(t, 0.35, 0.5)
    arrow_color = lerp_color(theme.background, theme.secondary, arrow_p)
    ay0, ay1 = h * 0.44, h * 0.5
    draw.line((w / 2, ay0, w / 2, ay1), fill=arrow_color, width=max(2, round(h * 0.004)))
    draw.polygon([(w / 2 - h * 0.012, ay1 - h * 0.012), (w / 2 + h * 0.012, ay1 - h * 0.012), (w / 2, ay1 + h * 0.006)], fill=arrow_color)

    p_after = anim.ease_out_cubic(anim.phase(t, 0.5, 0.85))
    scale = anim.scale_in(t, 0.5, 0.85, from_scale=0.8)
    y_after = h * 0.62
    color_after = lerp_color(theme.background, theme.positive, p_after)
    canvas.draw_text(draw, (w / 2, y_after), str(after.get("label", "")).upper(), f_label, color_after, bold=True)
    f_after_value = canvas.font(max(1, round(h * 0.06 * scale)))
    canvas.draw_text(draw, (w / 2, y_after + h * 0.07), str(after.get("displayValue") or ""), f_after_value, color_after, bold=True)
    return image


def render_timeline(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.15)
    steps = data.get("steps") or []
    n = len(steps)
    y = h * 0.45
    x0, x1 = w * 0.12, w * 0.88
    line_progress = anim.ease_out_cubic(anim.phase(t, 0.1, 0.75))
    line_color = lerp_color(theme.background, theme.secondary, 1.0 if line_progress > 0 else 0.0)
    if n > 1:
        draw.line((x0, y, x0 + (x1 - x0) * line_progress, y), fill=line_color, width=max(2, round(h * 0.004)))
    f_label = canvas.font(round(h * 0.024))
    for i, step in enumerate(steps):
        p = anim.stagger(t, i, n, start=0.05, span=0.7, item_duration=0.35)
        cx = x0 if n <= 1 else x0 + (x1 - x0) * i / (n - 1)
        r = h * 0.014 * anim.scale_in(t, 0, 1, from_scale=0.3) if p > 0 else 0
        dot_color = lerp_color(theme.background, theme.primary, p)
        if r > 0:
            draw.ellipse((cx - r, y - r, cx + r, y + r), fill=dot_color)
        label_color = lerp_color(theme.background, theme.text, p)
        canvas.draw_text(draw, (cx, y + h * 0.05), str(step).upper(), f_label, label_color, bold=True)
    return image


def render_compound_growth(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.14)
    rows = data.get("data") or []
    n = len(rows)
    top_ratio, bottom_ratio = 0.28, 0.85
    step_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    for i, row in enumerate(rows):
        p = anim.stagger(t, i, n, start=0.05, span=0.75, item_duration=0.45)
        cy = top_ratio * h + step_h * i + step_h / 2
        is_last = i == n - 1
        color = theme.accent if is_last else theme.primary
        text_color = lerp_color(theme.background, color, p)
        label_color = lerp_color(theme.background, theme.muted_text, p)
        base_size = h * (0.03 + 0.015 * (i / max(n - 1, 1)))
        f_value = canvas.font(round(base_size))
        f_label = canvas.font(round(h * 0.02))
        canvas.draw_text(draw, (w * 0.62, cy), str(row.get("displayValue") or ""), f_value, text_color, anchor="lm", bold=True)
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
    n = len(items)
    top_ratio, bottom_ratio = 0.26, 0.85
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    f_item = canvas.font(round(h * 0.028))
    icon_span = h * 0.03
    for i, item in enumerate(items):
        p = anim.stagger(t, i, n, start=0.05, span=0.75, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        offset = (1 - p) * h * 0.02
        check_color = lerp_color(theme.background, theme.positive, p)
        box = (w * 0.12, cy - icon_span / 2 + offset, w * 0.12 + icon_span, cy + icon_span / 2 + offset)
        icons.draw_icon(draw, "check", box, check_color)
        text_color = lerp_color(theme.background, theme.text, p)
        canvas.draw_text(draw, (w * 0.12 + icon_span * 1.6, cy + offset), str(item), f_item, text_color, anchor="lm", bold=True)
    return image


def render_warning(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    panel_box = (w * 0.08, h * 0.28, w * 0.92, h * 0.62)
    image, draw = canvas.panel(image, panel_box, h * 0.03, theme.negative, alpha=round(30 * anim.fade_in(t, 0, 0.2)))
    pulse = anim.pulse(t, start=0.3, amplitude=0.06)
    icon_span = h * 0.07 * pulse
    cx = w / 2
    icon_cy = h * 0.38
    icons.draw_icon(draw, "warning", (cx - icon_span / 2, icon_cy - icon_span / 2, cx + icon_span / 2, icon_cy + icon_span / 2), lerp_color(theme.background, theme.negative, anim.fade_in(t, 0, 0.2)))
    f_title = canvas.font(round(h * 0.04))
    title_color = lerp_color(theme.background, theme.text, anim.fade_in(t, 0.1, 0.3))
    canvas.draw_text(draw, (cx, h * 0.48), str(data.get("title") or "").upper(), f_title, title_color, bold=True)
    if data.get("label"):
        f_label = canvas.font(round(h * 0.025))
        label_color = lerp_color(theme.background, theme.secondary, anim.fade_in(t, 0.25, 0.45))
        canvas.draw_text(draw, (cx, h * 0.55), str(data["label"]).upper(), f_label, label_color, bold=True)
    return image


def render_formula(data: dict, t: float, theme: Theme, size: tuple[int, int]) -> Image.Image:
    image, draw = canvas.new_frame(size, theme.background)
    w, h = size
    _title(image, draw, theme, size, data.get("title") or "", t, y_ratio=0.16)
    terms = data.get("terms") or []
    n = len(terms)
    top_ratio, bottom_ratio = 0.3, 0.8
    row_h = (bottom_ratio - top_ratio) * h / max(n, 1)
    for i, term in enumerate(terms):
        p = anim.stagger(t, i, n, start=0.1, span=0.7, item_duration=0.4)
        cy = top_ratio * h + row_h * i + row_h / 2
        offset = anim.slide_up(t, 0, 1, distance=20) * (1 - p) if p < 1 else 0
        is_result = str(term).strip().startswith("=")
        color = theme.accent if is_result else theme.text
        text_color = lerp_color(theme.background, color, p)
        base_size = h * (0.036 if is_result else 0.03)
        f = canvas.font(round(base_size))
        canvas.draw_text(draw, (w / 2, cy + offset), str(term).upper(), f, text_color, bold=True)
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
        _label(image, draw, theme, size, str(data["label"]), t, y_ratio=0.48 + line_h * len(lines) / h + 0.06, start=0.35)
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
