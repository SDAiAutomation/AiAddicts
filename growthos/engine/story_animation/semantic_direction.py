"""Deterministic, zero-API visual direction for rig_v1.

Only chooses existing shot types and camera moves. The optional, author-controlled
shot.intent provides context; without it the renderer keeps its legacy behavior.
No generated code, paths, or assets enter the render timeline.
"""
from __future__ import annotations

import re

# Small, auditable vocabulary. Do not treat keyword matching as story comprehension.
_REVEAL = re.compile(r"\b(reveal|discover|realiz|secret|truth|révél|découvr|vérité)\w*", re.I)
# only what the scene can really show: its single prop is the alarm clock
_OBJECT = re.compile(r"\b(clock|alarm|horloge|r[ée]veil)\w*", re.I)
_REACTION = re.compile(r"\b(fear|afraid|shock|surpris|peur|inquiet|panique|hésit)\w*", re.I)


def direction(intent: str, actors: list[dict], speaker: str) -> dict | None:
    """Return an achievable visual treatment or None for the existing planner.

    The renderer currently supports only alarm_clock as a prop. An insert shot
    without that asset would be misleading, so object inserts require it.
    """
    if not isinstance(intent, str) or not intent.strip():
        return None
    # an insert hides the faces: only while the narrator talks, never over a character's line
    if speaker == "narrator" and _OBJECT.search(intent) and any("alarm_clock" in a.get("props", []) for a in actors):
        return {"shot_type": "insert", "camera": {"move": "static", "zoom_from": 2.8, "zoom_to": 2.8}}
    if _REVEAL.search(intent):
        return {"shot_type": "close_up", "camera": {"move": "push_in", "zoom_from": 1.8, "zoom_to": 2.2}} if speaker in ("pip", "ros") else {"shot_type": "medium", "camera": {"move": "push_in", "zoom_from": 1.2, "zoom_to": 1.35}}
    if _REACTION.search(intent) and actors:
        return {"shot_type": "medium", "camera": {"move": "static", "zoom_from": 1.3, "zoom_to": 1.3}}
    return None
