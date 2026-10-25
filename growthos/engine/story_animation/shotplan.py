"""Shot plan for the rig_v1 scene: the contract's shots joined with the measured timeline (pure, no IO, not wired anywhere new).

One shot per spoken line. Cut times come from the pauses of the measured audio (`timeline.shot_cuts`); everything else the
scene needs (setting, framing, who stands where and faces which way, mood, gesture, props) is copied from the validated
contract, with role names (`pip`, `ros`) in place of character ids because the packaged scene draws roles.
"""
from __future__ import annotations

from . import timeline as timeline_lib

# closed list the scene knows how to draw (the contract catalog may hold more ids than the scene can show)
BACKGROUNDS = {"clock_shop": "bg_shop", "factory_alley": "bg_alley", "cafe_terrace": "bg_cafe", "street": "bg_street"}
WIDE = (1.0, 1.08)
MEDIUM = (1.25, 1.35)  # wide enough for one actor on each side of the frame
INSERT = (2.8, 3.2)
CLOSE_UP = {"pip": (2.2, 2.7), "ros": (1.8, 2.25)}


def default_zoom(shot_type: str, speaker_role: str) -> tuple:
    if shot_type == "close_up":
        return CLOSE_UP.get(speaker_role, WIDE)  # a narrator shot has no speaker to frame (the contract refuses it anyway)
    return {"wide": WIDE, "medium": MEDIUM, "insert": INSERT}[shot_type]


def build_shot_plan(story: dict, tl: dict, roles: dict) -> list:
    """`roles`: character id -> rig role. Returns [{index, start, end, setting, background, shot_type, camera, speaker, actors, transition_in}]."""
    shots = story["shots"]
    if len(shots) != len(tl["lines"]):
        raise ValueError("the scene needs exactly one shot per spoken line")
    cuts = timeline_lib.shot_cuts(tl)
    plan = []
    for i, shot in enumerate(shots):
        speaker = roles[shot["speaker_id"]]
        camera = shot.get("camera")
        preset = default_zoom(shot["shot_type"], speaker)
        if camera is None:
            move, z0, z1 = "push_in", preset[0], preset[1]
        else:
            move = camera.get("move", "static")
            z0 = float(camera.get("zoom_from", preset[0]))
            z1 = float(camera.get("zoom_to", preset[1]))
            if move == "static":
                z1 = z0
        actors = [{
            "role": roles[a["character_id"]], "side": a["side"], "facing": a["facing"], "mood": a.get("mood", "neutral"),
            "gesture": a.get("gesture_id", "idle"), "props": list(a.get("props", [])),
        } for a in shot["actors"]]
        plan.append({
            "index": i, "start": cuts[i], "end": cuts[i + 1], "setting": shot["setting_id"],
            "background": BACKGROUNDS.get(shot["setting_id"], "bg_shop"), "shot_type": shot["shot_type"],
            "camera": {"move": move, "zoom_from": z0, "zoom_to": z1}, "speaker": speaker, "actors": actors,
            "transition_in": shot.get("transition_in", "cut"),
        })
    return plan
