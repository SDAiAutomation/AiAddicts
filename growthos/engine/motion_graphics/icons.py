"""Small vector icon set drawn with `ImageDraw` primitives — no icon-library
dependency, and every icon inherits the scene's theme color by construction
(it is drawn in that color, never loaded from a static asset).

Covers the categories requested for finance/business/productivity content:
money, wallet, bank, credit card, house, shopping, savings, investment,
chart, calendar, warning, check, cross, clock, percentage, target.
"""
from __future__ import annotations

from PIL import ImageDraw


def _line_width(box: tuple[float, float, float, float]) -> int:
    x0, y0, x1, y1 = box
    return max(2, round(min(x1 - x0, y1 - y0) * 0.07))


def _wallet(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    draw.rounded_rectangle((x0, y0 + (y1 - y0) * 0.15, x1, y1 - (y1 - y0) * 0.05), radius=(x1 - x0) * 0.12, outline=color, width=w)
    cx = x1 - (x1 - x0) * 0.22
    cy = y0 + (y1 - y0) * 0.55
    r = (x1 - x0) * 0.09
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)


def _bank(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    cx = (x0 + x1) / 2
    top = y0 + (y1 - y0) * 0.05
    draw.polygon([(cx, top), (x1, top + (y1 - y0) * 0.22), (x0, top + (y1 - y0) * 0.22)], outline=color, width=w)
    base_y = y1 - (y1 - y0) * 0.12
    draw.line((x0, base_y, x1, base_y), fill=color, width=w)
    for frac in (0.18, 0.42, 0.58, 0.82):
        px = x0 + (x1 - x0) * frac
        draw.line((px, top + (y1 - y0) * 0.28, px, base_y), fill=color, width=w)


def _credit_card(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    top = y0 + (y1 - y0) * 0.22
    bottom = y1 - (y1 - y0) * 0.22
    draw.rounded_rectangle((x0, top, x1, bottom), radius=(bottom - top) * 0.18, outline=color, width=w)
    stripe_y = top + (bottom - top) * 0.32
    draw.line((x0, stripe_y, x1, stripe_y), fill=color, width=w)


def _house(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    cx = (x0 + x1) / 2
    roof_y = y0 + (y1 - y0) * 0.15
    wall_top = y0 + (y1 - y0) * 0.42
    wall_bottom = y1 - (y1 - y0) * 0.1
    draw.polygon([(cx, roof_y), (x1, wall_top), (x0, wall_top)], outline=color, width=w)
    draw.rectangle((x0 + (x1 - x0) * 0.12, wall_top, x1 - (x1 - x0) * 0.12, wall_bottom), outline=color, width=w)


def _shopping_cart(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    basket = (x0 + (x1 - x0) * 0.15, y0 + (y1 - y0) * 0.3, x1 - (x1 - x0) * 0.05, y0 + (y1 - y0) * 0.62)
    draw.line((x0, y0 + (y1 - y0) * 0.18, basket[0], basket[1]), fill=color, width=w)
    draw.rectangle(basket, outline=color, width=w)
    r = (x1 - x0) * 0.07
    for frac in (0.28, 0.62):
        cx = x0 + (x1 - x0) * frac
        cy = y1 - (y1 - y0) * 0.12
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)


def _piggy_bank(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    body = (x0, y0 + (y1 - y0) * 0.28, x1 - (x1 - x0) * 0.12, y1 - (y1 - y0) * 0.15)
    draw.rounded_rectangle(body, radius=(body[3] - body[1]) * 0.4, outline=color, width=w)
    slot_x = (body[0] + body[2]) / 2
    draw.line((slot_x - (x1 - x0) * 0.08, body[1] - w, slot_x + (x1 - x0) * 0.08, body[1] - w), fill=color, width=w)
    leg_y0, leg_y1 = body[3], y1
    for frac in (0.18, 0.62):
        lx = body[0] + (body[2] - body[0]) * frac
        draw.line((lx, leg_y0, lx, leg_y1), fill=color, width=w)


def _investment_chart(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    points = [(x0, y1 * 0.9 + y0 * 0.1), (x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.55),
              (x0 + (x1 - x0) * 0.58, y0 + (y1 - y0) * 0.68), (x1, y0 + (y1 - y0) * 0.1)]
    draw.line(points, fill=color, width=w, joint="curve")
    ax, ay = points[-1]
    arrow = (x1 - x0) * 0.12
    draw.line((ax, ay, ax - arrow, ay), fill=color, width=w)
    draw.line((ax, ay, ax, ay + arrow), fill=color, width=w)


def _bar_chart_icon(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = max(2, round((x1 - x0) * 0.14))
    gap = (x1 - x0) * 0.1
    heights = (0.4, 0.75, 0.55)
    bx = x0
    for h in heights:
        draw.rectangle((bx, y1 - (y1 - y0) * h, bx + w, y1), outline=color, width=max(2, w // 5))
        bx += w + gap


def _calendar(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    top = y0 + (y1 - y0) * 0.18
    draw.rounded_rectangle((x0, top, x1, y1), radius=(x1 - x0) * 0.08, outline=color, width=w)
    draw.line((x0, top + (y1 - top) * 0.28, x1, top + (y1 - top) * 0.28), fill=color, width=w)
    for frac in (0.28, 0.72):
        lx = x0 + (x1 - x0) * frac
        draw.line((lx, y0, lx, top + (y1 - top) * 0.15), fill=color, width=w)


def _warning(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    cx = (x0 + x1) / 2
    draw.polygon([(cx, y0), (x1, y1 - (y1 - y0) * 0.05), (x0, y1 - (y1 - y0) * 0.05)], outline=color, width=w)
    draw.line((cx, y0 + (y1 - y0) * 0.35, cx, y0 + (y1 - y0) * 0.68), fill=color, width=w)
    r = w * 0.9
    draw.ellipse((cx - r, y1 - (y1 - y0) * 0.22 - r, cx + r, y1 - (y1 - y0) * 0.22 + r), fill=color)


def _check(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    draw.line([(x0, y0 + (y1 - y0) * 0.55), (x0 + (x1 - x0) * 0.4, y1 - (y1 - y0) * 0.15), (x1, y0)], fill=color, width=w, joint="curve")


def _cross(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    draw.line((x0, y0, x1, y1), fill=color, width=w)
    draw.line((x0, y1, x1, y0), fill=color, width=w)


def _clock(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    draw.ellipse(box, outline=color, width=w)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    draw.line((cx, cy, cx, y0 + (y1 - y0) * 0.28), fill=color, width=w)
    draw.line((cx, cy, x0 + (x1 - x0) * 0.68, cy), fill=color, width=w)


def _percent(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    r = (x1 - x0) * 0.16
    draw.ellipse((x0, y0, x0 + 2 * r, y0 + 2 * r), outline=color, width=w)
    draw.ellipse((x1 - 2 * r, y1 - 2 * r, x1, y1), outline=color, width=w)
    draw.line((x0, y1, x1, y0), fill=color, width=w)


def _target(draw: ImageDraw.ImageDraw, box, color) -> None:
    x0, y0, x1, y1 = box
    w = _line_width(box)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for scale in (1.0, 0.62, 0.24):
        rx, ry = (x1 - x0) * scale / 2, (y1 - y0) * scale / 2
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=color, width=w)


ICONS = {
    "money": _wallet,
    "wallet": _wallet,
    "bank": _bank,
    "credit_card": _credit_card,
    "card": _credit_card,
    "house": _house,
    "shopping_cart": _shopping_cart,
    "shopping": _shopping_cart,
    "savings": _piggy_bank,
    "piggy_bank": _piggy_bank,
    "investment": _investment_chart,
    "chart": _bar_chart_icon,
    "calendar": _calendar,
    "warning": _warning,
    "check": _check,
    "cross": _cross,
    "clock": _clock,
    "percentage": _percent,
    "percent": _percent,
    "target": _target,
}


def draw_icon(draw: ImageDraw.ImageDraw, name: str | None, box, color) -> bool:
    """Draws `name` inside `box`, returns whether anything was drawn. An
    unknown/missing icon draws nothing rather than failing the scene — see
    the fallback rule in the Motion Graphics spec ("if an icon is
    unavailable, render without the icon")."""
    renderer = ICONS.get((name or "").strip().lower())
    if not renderer:
        return False
    renderer(draw, box, color)
    return True
