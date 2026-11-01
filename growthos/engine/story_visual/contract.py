"""Routage worker du récit illustré, derrière un drapeau ÉTEINT par défaut (même schéma que `story_animation.contract`).

Un script `content_format: "story_visual"` portant un `story_plan` est « visuel ». Drapeau éteint : il est refusé AVANT toute
réservation de crédit ou appel fournisseur. Tout autre script (Standard, Quiz, Story animé) renvoie "legacy" : rien ne change.
"""
from __future__ import annotations

import os

CONTENT_FORMAT = "story_visual"


class VisualDisabled(RuntimeError):
    """Récit illustré reçu par un worker dont le drapeau est éteint."""


def visual_enabled() -> bool:
    return os.environ.get("STORY_VISUAL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def is_visual(script) -> bool:
    return isinstance(script, dict) and script.get("content_format") == CONTENT_FORMAT


def route_for(script, enabled: bool | None = None) -> str:
    """"legacy" ou "visual". Un récit illustré avec le drapeau éteint lève `VisualDisabled`."""
    if not is_visual(script):
        return "legacy"
    if not (visual_enabled() if enabled is None else enabled):
        raise VisualDisabled("illustrated stories are not enabled")
    return "visual"
