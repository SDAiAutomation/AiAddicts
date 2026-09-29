"""Motion Graphics visual style: programmatic infographic/data-viz scenes
rendered locally (Pillow + ffmpeg) instead of AI images — see `schema.py` for
the per-block contract `growthos-web` must emit, and `renderer.py` for how a
scene becomes a per-block `.mp4` clip consumed by `engine/video.py` exactly
like a stock-footage clip.

Designed to plug into `engine/visuals.py` as an alternative per-block visual
source, never as a replacement for it: existing visual styles (AI images,
Pexels stock, flat color) are untouched.
"""
from .renderer import render_scene_clip, resolve_scene
from .schema import FALLBACK_SCENE_TYPE, SCENE_TYPES, validate_scene
from .theme import DEFAULT_THEME, Theme, resolve_theme

__all__ = [
    "render_scene_clip",
    "resolve_scene",
    "validate_scene",
    "SCENE_TYPES",
    "FALLBACK_SCENE_TYPE",
    "Theme",
    "DEFAULT_THEME",
    "resolve_theme",
]
