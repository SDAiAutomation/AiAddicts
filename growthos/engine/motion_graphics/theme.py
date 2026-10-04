"""Design tokens for Motion Graphics.

A strong neutral default so the renderer works for any Faceloop account, not
just one niche (see the module docstring in `engine/motion_graphics/__init__`
for why this must never become account-specific). A script may override any
subset via its `motion_graphics_theme` field — the same "resolved once,
reused everywhere" pattern as `engine/image_style_bible.resolve_style_bible`.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

THEME_VERSION = "1.1.0"

# Font families a theme can select. Names must match the keys of
# `canvas._FONT_SPECS` (a test keeps both in step). "poppins" is the historical
# font: a theme that does not name a family renders exactly as before.
FONT_FAMILIES = ("poppins", "ibm_plex_sans", "nunito")
DEFAULT_FONT_FAMILY = "poppins"


@dataclass(frozen=True)
class Theme:
    background: str = "#16233A"
    primary: str = "#22D3EE"
    secondary: str = "#94A3B8"
    accent: str = "#F59E0B"
    text: str = "#F8FAFC"
    muted_text: str = "#94A3B8"
    positive: str = "#22C55E"
    negative: str = "#F87171"
    border_radius: int = 28
    font_family: str = DEFAULT_FONT_FAMILY


DEFAULT_THEME = Theme()

_FIELD_NAMES = {f.name for f in fields(Theme)}

# Named palettes a script can select via `motion_graphics_theme: {"preset": "<name>"}`
# instead of spelling out every hex value (see resolve_theme below). Each
# preset only overrides background/primary/secondary/accent — `positive`/
# `negative` stay the universal success/alert semantics (checkmarks,
# warning panels) across every preset, and `text`/`muted_text`/
# `border_radius` stay the same for legibility, so switching preset never
# breaks contrast or layout, only mood.
#
# Chosen from a 2026-10 review of finance-content color research (trust /
# growth / risk / premium / neutral moods) — the motivation was that every
# Motion Graphics video previously rendered with DEFAULT_THEME and nothing
# else, so every script in every niche/account looked identical regardless
# of topic. "classic" is DEFAULT_THEME itself, named so a caller can select
# it explicitly instead of omitting `preset`.
THEME_PRESETS: dict[str, Theme] = {
    "classic": DEFAULT_THEME,
    "trust_blue": replace(DEFAULT_THEME, background="#0A1A2F", primary="#2E86DE", secondary="#6FA8DC", accent="#F5A623", font_family="ibm_plex_sans"),
    "growth_green": replace(DEFAULT_THEME, background="#07241A", primary="#10B981", secondary="#6FCF97", accent="#FACC15", font_family="nunito"),
    "risk_red": replace(DEFAULT_THEME, background="#2B0F12", primary="#F4511E", secondary="#FFAB91", accent="#DC2626"),
    "premium_indigo": replace(DEFAULT_THEME, background="#13113A", primary="#5C6BC0", secondary="#9FA8DA", accent="#D4AF37", font_family="ibm_plex_sans"),
    "neutral": replace(DEFAULT_THEME, background="#1E1E1E", primary="#CBD5E1", secondary="#64748B", accent="#E2E8F0"),
}


def resolve_theme(overrides: dict | None) -> Theme:
    """A script's `motion_graphics_theme`, resolved to a concrete `Theme`.

    An optional `"preset"` key (one of THEME_PRESETS) selects the base
    palette instead of plain DEFAULT_THEME; any other recognised Theme
    field in the same dict still overrides on top of it, so a script can
    pick a preset AND tweak one color. No `"preset"` key, or an unknown
    one, resolves to DEFAULT_THEME as the base — exactly the behaviour
    before presets existed, so every script/test written before this
    feature is unaffected.
    """
    if not overrides or not isinstance(overrides, dict):
        return DEFAULT_THEME
    preset_name = str(overrides.get("preset") or "").strip().lower()
    base = THEME_PRESETS.get(preset_name, DEFAULT_THEME)
    safe_overrides = {
        key: value
        for key, value in overrides.items()
        if key in _FIELD_NAMES and isinstance(value, (str, int)) and str(value).strip()
    }
    if not safe_overrides:
        return base
    resolved = replace(base, **safe_overrides)
    if resolved.font_family not in FONT_FAMILIES:
        # An unknown family never reaches the renderer: keep the preset's own.
        resolved = replace(resolved, font_family=base.font_family)
    return resolved


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
