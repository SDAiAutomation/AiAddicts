"""Shot plan for the rig_v1 scene: the contract's shots joined with the measured timeline (pure, no IO, not wired anywhere new).

One shot per spoken line. Cut times come from the pauses of the measured audio (`timeline.shot_cuts`); everything else the
scene needs (setting, framing, who stands where and faces which way, mood, gesture, props) is copied from the validated
contract, with role names (`pip`, `ros`) in place of character ids because the packaged scene draws roles.
"""
from __future__ import annotations

from . import timeline as timeline_lib, visual_props

# closed list the scene knows how to draw (the contract catalog may hold more ids than the scene can show)
# setting id -> background picture of the pack. The last three reuse a picture of the pack and add procedural elements drawn by the
# scene (a growing queue, rain, a shop at night): the setting id itself tells the scene what to add.
BACKGROUNDS = {"clock_shop": "bg_shop", "factory_alley": "bg_alley", "cafe_terrace": "bg_cafe", "street": "bg_street",
               "street_queue": "bg_street", "street_rain": "bg_street", "clock_shop_closed": "bg_shop"}
WIDE = (1.0, 1.08)
MEDIUM = (1.25, 1.35)  # wide enough for one actor on each side of the frame
INSERT = (2.8, 3.2)
CLOSE_UP = {"pip": (2.2, 2.7), "ros": (1.8, 2.25)}


def default_zoom(shot_type: str, speaker_role: str) -> tuple:
    if shot_type == "close_up":
        return CLOSE_UP.get(speaker_role, WIDE)  # a narrator shot has no speaker to frame (the contract refuses it anyway)
    return {"wide": WIDE, "medium": MEDIUM, "insert": INSERT}[shot_type]


BEAT_SECONDS = 4.0        # a narrated shot is cut into beats of about this length
MIN_NARRATED_SPLIT_S = 8.0  # shorter narrated shots stay a single beat
MAX_BEATS = 5
# what a listener does while the narrator talks, in turn; only used where the story leaves the actor at rest (idle, neutral)
LISTENER_POSES = {"pip": ["idle", "wring", "shrug", "idle", "wring"], "ros": ["hands_on_hips", "idle", "shrug", "hands_on_hips", "idle"]}
REACTION_MOODS = ["puzzled", "worry", "surprise"]
# composition of each beat, in turn: a wide establishing push, a reaction on a listener, the setting alone, a two-shot pan, a second reaction
BEATS = [
    {"kind": "wide", "move": "push_in", "zoom": (1.0, 1.1)},
    {"kind": "reaction", "listener": 0},
    {"kind": "empty", "move": "pan_right", "zoom": (1.05, 1.05)},
    {"kind": "medium", "move": "pan_left", "zoom": (1.25, 1.35)},
    {"kind": "reaction", "listener": 1},
]


def narrated_beats(entry: dict, start_index: int) -> list:
    """Cuts one long narrator shot into visual beats (same speaker, same setting, same words): the camera and the picture change
    every few seconds instead of one composition staying on screen. Deterministic, no new asset, nothing the author wrote is changed:
    only actors left at rest get a listening pose, and a reaction beat gives the framed listener a mood."""
    duration = entry["end"] - entry["start"]
    n = min(MAX_BEATS, int(duration // BEAT_SECONDS))
    if entry["speaker"] != "narrator" or duration < MIN_NARRATED_SPLIT_S or n < 2 or not entry["actors"]:
        return [dict(entry, index=start_index)]   # unchanged: the scene reads the optional focus / empty / beat keys with defaults
    beats = []
    for k in range(n):
        spec = BEATS[k % len(BEATS)]
        a, b = entry["start"] + duration * k / n, entry["start"] + duration * (k + 1) / n
        actors = [dict(x) for x in entry["actors"]]
        for x in actors:
            if x["gesture"] == "idle" and x["mood"] == "neutral" and x["role"] in LISTENER_POSES:
                poses = LISTENER_POSES[x["role"]]
                x["gesture"] = poses[k % len(poses)]
        focus, empty = None, False
        shot_type, move, zoom = "wide", "static", (1.0, 1.0)
        if spec["kind"] == "reaction":
            target = actors[spec["listener"] % len(actors)]
            focus = target["role"]
            target["mood"] = REACTION_MOODS[(k // 2) % len(REACTION_MOODS)]
            shot_type, move, zoom = "close_up", "push_in", CLOSE_UP.get(focus, WIDE)
        else:
            shot_type, move, zoom = spec["kind"] if spec["kind"] != "empty" else "wide", spec["move"], spec["zoom"]
            empty = spec["kind"] == "empty"
        beats.append(dict(entry, index=start_index + k, start=round(a, 3), end=round(b, 3), shot_type=shot_type, actors=actors,
                          camera={"move": move, "zoom_from": zoom[0], "zoom_to": zoom[1]}, focus=focus, empty=empty, beat=k,
                          transition_in=entry["transition_in"] if k == 0 else "cut"))
    beats[-1]["end"] = entry["end"]
    return beats


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
            "objects": visual_props.schedule(str(tl["lines"][i]["text"]), float(tl["lines"][i]["start"]), float(tl["lines"][i]["dur"])),
        })
    expanded = []
    for entry in plan:
        expanded += narrated_beats(entry, len(expanded))
    return expanded
