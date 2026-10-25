"""Compile the existing measured story timeline and shot plan for the generic Godot rig.

No model, TTS call or new job state lives here. Speech timing and `c/o/r` mouth
cues come from timeline.py; acting, settings and camera come from shotplan.py.
Unsupported input is refused, not silently mapped to another action.
"""
from __future__ import annotations

import math

from . import rig_v2, timeline as timeline_lib
from .renderer import RenderError

SIDE_X = {"left": 0.27, "center": 0.50, "right": 0.73}


def _frame(seconds: object, fps: int) -> int:
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise RenderError("measured timeline contains an invalid timestamp")
    return round(seconds * fps)


def compile_measured(timeline: dict, shot_plan: list[dict], role_to_character: dict[str, str]) -> dict:
    """Turn seconds into continuous frame boundaries and measured per-frame cues.

    The caller supplies the explicit validated mapping of legacy rig roles to
    manifest IDs. A narrator has audio/subtitles but no body and needs no map.
    """
    if not isinstance(timeline, dict) or timeline.get("fps") != rig_v2.FPS:
        raise RenderError("measured timeline must use the generic rig FPS")
    fps = rig_v2.FPS
    total_s = timeline.get("total")
    if type(total_s) not in (int, float) or not math.isfinite(total_s) or total_s <= 0:
        raise RenderError("measured timeline total is invalid")
    total = math.ceil(total_s * fps)
    if not 1 <= total <= rig_v2.MAX_FRAMES or not isinstance(shot_plan, list) or not shot_plan:
        raise RenderError("measured timeline duration or shot plan is invalid")
    if not isinstance(role_to_character, dict) or not role_to_character or not all(
        isinstance(role, str) and isinstance(character, str) and rig_v2.rig_manifest._id(character)
        for role, character in role_to_character.items()
    ) or len(set(role_to_character.values())) != len(role_to_character):
        raise RenderError("rig role mapping is invalid")
    lines = timeline.get("lines")
    if not isinstance(lines, list) or not lines:
        raise RenderError("measured timeline has no voice lines")
    for line in lines:
        if (not isinstance(line, dict) or not isinstance(line.get("who"), str)
                or line["who"] not in role_to_character and line["who"] != "narrator"
                or type(line.get("start")) not in (int, float) or type(line.get("end")) not in (int, float)
                or not math.isfinite(line["start"]) or not math.isfinite(line["end"])
                or not 0 <= line["start"] < line["end"] <= total_s
                or not isinstance(line.get("mouth"), str) or not line["mouth"]
                or set(line["mouth"]) - {"c", "o", "r"}):
            raise RenderError("measured voice line has unsupported mouth cues or speaker")
    shots, cursor = [], 0
    for index, source in enumerate(shot_plan):
        if not isinstance(source, dict) or _frame(source.get("start"), fps) != cursor:
            raise RenderError(f"shot plan[{index}] does not follow the measured timeline")
        end = total if index == len(shot_plan) - 1 else _frame(source.get("end"), fps)
        if end <= cursor or end > total:
            raise RenderError(f"shot plan[{index}] has invalid frame boundaries")
        actors = []
        source_actors = [] if source.get("empty", False) else source.get("actors", [])
        if not isinstance(source_actors, list):
            raise RenderError(f"shot plan[{index}] actors are invalid")
        for actor in source_actors:
            if (not isinstance(actor, dict) or not isinstance(actor.get("role"), str) or actor["role"] not in role_to_character
                    or not isinstance(actor.get("side"), str) or actor["side"] not in SIDE_X):
                raise RenderError(f"shot plan[{index}] contains an unmapped actor")
            role = actor["role"]
            mouth = "".join(timeline_lib.mouth_at(timeline, role, frame) for frame in range(cursor, end))
            actors.append({
                "character_id": role_to_character[role], "x": SIDE_X[actor["side"]],
                "facing": actor["facing"], "action": actor["gesture"], "expression": actor["mood"],
                "mouth_track": mouth,
            })
        camera = source.get("camera")
        shots.append({
            "start_frame": cursor, "end_frame": end, "setting": source.get("setting"),
            "camera": dict(camera) if isinstance(camera, dict) else camera,
            "transition": source.get("transition_in"), "actors": actors, "subtitle": "",
        })
        cursor = end
    raw_subs = timeline.get("subs", [])
    if not isinstance(raw_subs, list):
        raise RenderError("measured subtitles must be a list")
    subs, previous_end = [], 0
    for index, sub in enumerate(raw_subs):
        if not isinstance(sub, dict) or not isinstance(sub.get("text"), str):
            raise RenderError(f"measured subtitle[{index}] is invalid")
        a, b = _frame(sub.get("start"), fps), _frame(sub.get("end"), fps)
        if not previous_end <= a < b <= total:
            raise RenderError(f"measured subtitle[{index}] cannot be represented at {fps} FPS")
        subs.append({"start_frame": a, "end_frame": b, "text": sub["text"]})
        previous_end = b
    return {
        "rig_schema_version": 1, "fps": fps, "total_frames": total,
        "characters": list(role_to_character.values()), "shots": shots, "subs": subs,
    }
