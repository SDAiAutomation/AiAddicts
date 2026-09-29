"""Design tokens for Motion Graphics.

A strong neutral default so the renderer works for any Faceloop account, not
just one niche (see the module docstring in `engine/motion_graphics/__init__`
for why this must never become account-specific). A script may override any
subset via its `motion_graphics_theme` field — the same "resolved once,
reused everywhere" pattern as `engine/image_style_bible.resolve_style_bible`.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

THEME_VERSION = "1.0.0"


@dataclass(frozen=True)
class Theme:
    background: str = "#0B1220"
    primary: str = "#22D3EE"
    secondary: str = "#94A3B8"
    accent: str = "#F59E0B"
    text: str = "#F8FAFC"
    muted_text: str = "#94A3B8"
    positive: str = "#22C55E"
    negative: str = "#F87171"
    border_radius: int = 28


DEFAULT_THEME = Theme()

_FIELD_NAMES = {f.name for f in fields(Theme)}


def resolve_theme(overrides: dict | None) -> Theme:
    if not overrides or not isinstance(overrides, dict):
        return DEFAULT_THEME
    safe_overrides = {
        key: value
        for key, value in overrides.items()
        if key in _FIELD_NAMES and isinstance(value, (str, int)) and str(value).strip()
    }
    if not safe_overrides:
        return DEFAULT_THEME
    return replace(DEFAULT_THEME, **safe_overrides)


def hex_to_rgb(color: str, alpha: int | None = None) -> tuple[int, ...]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    rgb = tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    return (*rgb, alpha) if alpha is not None else rgb


def with_alpha(color: str, alpha: int) -> tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(color)
    return r, g, b, alpha


def lerp_color(from_color: str, to_color: str, t: float) -> tuple[int, int, int]:
    """Blends two colors — used as a cheap stand-in for an opacity fade
    against a scene's flat background, avoiding per-glyph alpha compositing
    for every text draw."""
    t = min(max(t, 0.0), 1.0)
    a = hex_to_rgb(from_color)
    b = hex_to_rgb(to_color)
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
