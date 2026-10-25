"""Review of how well the pictures follow the words of a story (pure, no IO, never blocking).

Quality comes from the story first; this module only checks that what is said can be SEEN: a long narration needs something on
screen that belongs to it, an object that is named should appear, and the same composition should not stay for a whole scene.
Each issue is {shot, kind, text} so a human or a generator can fix the plan."""
from __future__ import annotations

import re

from . import visual_props

LONG_NARRATION_CHARS = 110       # a narrator shot longer than this has to carry something to look at
MAX_SAME_COMPOSITION = 2         # three shots in a row with the same setting and framing are a visual stall
_QUOTED = re.compile(r"[«\"“]\s*([^»\"”]{1,40}?)\s*[»\"”]")


def _anchors(shot: dict) -> list:
    """What gives the eye something that belongs to the words of this shot."""
    text = shot.get("dialogue", "")
    found = [f"object:{oid}" for oid, _ in visual_props.mentions(text)]
    found += [f"card:{m.group(1)}" for m in _QUOTED.finditer(text) if len(m.group(1).split()) <= 3]
    if any(a.get("gesture_id", "idle") != "idle" or a.get("mood", "neutral") != "neutral" for a in shot.get("actors", [])):
        found.append("acting")
    if shot.get("shot_type") == "insert":
        found.append("insert")
    return found


def review(story: dict) -> list:
    issues, shots = [], story.get("shots", [])
    for i, shot in enumerate(shots):
        text = shot.get("dialogue", "")
        if shot.get("speaker_id") == "narrator" and len(text) >= LONG_NARRATION_CHARS and not _anchors(shot):
            issues.append({"shot": i, "kind": "narration_without_anchor",
                           "text": "long narration with nothing that belongs to it on screen: name an object, quote a key word, or give the actors a reaction"})
        for word in visual_props.undrawable(text):
            issues.append({"shot": i, "kind": "mentioned_not_drawn", "text": f"'{word}' is named but the scene cannot draw it yet"})
    run = 1
    for i in range(1, len(shots)):
        same = (shots[i]["setting_id"], shots[i]["shot_type"]) == (shots[i - 1]["setting_id"], shots[i - 1]["shot_type"])
        run = run + 1 if same else 1
        if run > MAX_SAME_COMPOSITION:
            issues.append({"shot": i, "kind": "same_composition", "text": f"{run} shots in a row with the same setting and framing"})
    return issues
