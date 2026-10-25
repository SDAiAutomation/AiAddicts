"""Offline generic cutout renderer. Existing rig_v1 and production routing are unchanged.

This renderer accepts a validated frame timeline and pack-local rig manifests.
There is no user-provided file path, script, or executable in the timeline.
"""
from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

from . import rig_manifest, rig_v1
from .renderer import CostEstimate, RenderError, RenderResult

PROJECT_DIR = Path(__file__).parent / "godot" / "rig_v2"
FPS, WIDTH, HEIGHT = 24, 1080, 1920
MAX_FRAMES = FPS * 200
_MOVES = {"static", "push_in", "pull_out", "pan_left", "pan_right"}
_TRANSITIONS = {"cut", "fade"}
SETTINGS = {"forest", "street", "street_queue", "street_rain", "clock_shop", "clock_shop_closed", "cafe_terrace", "factory_alley"}


def _finite(value: object, minimum: float, maximum: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def validate_timeline(timeline: object, pack_dir: Path) -> dict[str, dict]:
    required = {"rig_schema_version", "fps", "total_frames", "characters", "shots"}
    if not isinstance(timeline, dict) or not required <= set(timeline) or set(timeline) - required - {"subs"}:
        raise RenderError("generic rig timeline fields are invalid")
    if type(timeline["rig_schema_version"]) is not int or timeline["rig_schema_version"] != 1 or timeline["fps"] != FPS:
        raise RenderError("generic rig timeline version or fps is unsupported")
    total = timeline["total_frames"]
    if type(total) is not int or not 1 <= total <= MAX_FRAMES:
        raise RenderError("generic rig timeline length is invalid")
    ids = timeline["characters"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 6 or not all(isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
        raise RenderError("generic rig characters are invalid")
    rigs = {}
    for character_id in ids:
        # The manifest parser enforces simple IDs; build no path until that check passes.
        if not rig_manifest._id(character_id):
            raise RenderError("generic rig character id is unsafe")
        try:
            rigs[character_id] = rig_manifest.load_manifest(Path(pack_dir) / character_id / "rig.json", Path(pack_dir) / character_id)
        except (rig_manifest.RigManifestError, OSError) as exc:
            raise RenderError(f"generic rig character {character_id} is unusable: {exc}") from exc
        if rigs[character_id]["character_id"] != character_id:
            raise RenderError("generic rig character id differs from its manifest")
    shots = timeline["shots"]
    if not isinstance(shots, list) or not 1 <= len(shots) <= 200:
        raise RenderError("generic rig shots are invalid")
    cursor = 0
    for i, shot in enumerate(shots):
        label = f"shots[{i}]"
        if not isinstance(shot, dict) or set(shot) != {"start_frame", "end_frame", "setting", "camera", "transition", "actors", "subtitle"}:
            raise RenderError(f"{label} fields are invalid")
        a, b = shot["start_frame"], shot["end_frame"]
        if type(a) is not int or type(b) is not int or a != cursor or b <= a or b > total:
            raise RenderError(f"{label} frame boundaries are invalid")
        cursor = b
        if not isinstance(shot["setting"], str) or shot["setting"] not in SETTINGS:
            raise RenderError(f"{label} setting is unsupported")
        camera = shot["camera"]
        if not isinstance(camera, dict) or set(camera) != {"move", "zoom_from", "zoom_to"} or not isinstance(camera["move"], str) or camera["move"] not in _MOVES:
            raise RenderError(f"{label} camera is invalid")
        if not _finite(camera["zoom_from"], 0.8, 3) or not _finite(camera["zoom_to"], 0.8, 3):
            raise RenderError(f"{label} camera zoom is invalid")
        if not isinstance(shot["transition"], str) or shot["transition"] not in _TRANSITIONS or not isinstance(shot["subtitle"], str) or len(shot["subtitle"]) > 300:
            raise RenderError(f"{label} transition or subtitle is invalid")
        actors = shot["actors"]
        if not isinstance(actors, list) or len(actors) > min(3, len(ids)):
            raise RenderError(f"{label} actors are invalid")
        seen = set()
        for actor in actors:
            if not isinstance(actor, dict) or set(actor) != {"character_id", "x", "facing", "action", "expression", "mouth_track"}:
                raise RenderError(f"{label} actor fields are invalid")
            who = actor["character_id"]
            if not isinstance(who, str) or who not in rigs or who in seen:
                raise RenderError(f"{label} has an unknown or duplicate actor")
            seen.add(who)
            if (not _finite(actor["x"], 0.1, 0.9) or actor["facing"] not in ("left", "right")
                    or actor["action"] not in rigs[who]["actions"] or actor["expression"] not in rigs[who]["expressions"]
                    or not isinstance(actor["mouth_track"], str) or len(actor["mouth_track"]) != b - a
                    or set(actor["mouth_track"]) - {"c", "o", "r"}):
                raise RenderError(f"{label} actor instruction is unsupported")
    if cursor != total:
        raise RenderError("generic rig shots do not cover all frames")
    subs = timeline.get("subs", [])
    if not isinstance(subs, list) or len(subs) > 1000:
        raise RenderError("generic rig subtitles are invalid")
    previous_end = 0
    for i, sub in enumerate(subs):
        if not isinstance(sub, dict) or set(sub) != {"start_frame", "end_frame", "text"}:
            raise RenderError(f"subtitles[{i}] fields are invalid")
        a, b = sub["start_frame"], sub["end_frame"]
        if (type(a) is not int or type(b) is not int or not previous_end <= a < b <= total
                or not isinstance(sub["text"], str) or not sub["text"].strip() or len(sub["text"]) > 300):
            raise RenderError(f"subtitles[{i}] timing or text is invalid")
        previous_end = b
    return rigs


class RigV2Renderer:
    name = "rig_v2"
    version = "1"

    def __init__(self, godot_bin: str, ffmpeg: str = "ffmpeg", launcher: tuple[str, ...] = ()):  # offline only
        self.godot_bin, self.ffmpeg, self.launcher = godot_bin, ffmpeg, tuple(launcher)

    def estimate(self, total_seconds: float, tts_chars: int) -> CostEstimate:
        if not _finite(total_seconds, 0.001, 200) or tts_chars < 0:
            raise ValueError("invalid render estimate inputs")
        return CostEstimate(round(total_seconds * rig_v1.RENDER_RATIO_ESTIMATE, 1), tts_chars, 0)

    def render(self, timeline: dict, pack_dir: Path, workdir: Path, timeout_s: float = 600) -> RenderResult:
        validate_timeline(timeline, pack_dir)
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        timeline_file = rig_v1.confine(workdir / "timeline.json", workdir)
        avi = rig_v1.confine(workdir / "silent.avi", workdir)
        mp4 = rig_v1.confine(workdir / "silent.mp4", workdir)
        timeline_file.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        env = rig_v1.clean_env()
        cmd = [*self.launcher, self.godot_bin, "--path", str(PROJECT_DIR), "--rendering-driver", "opengl3",
               "--write-movie", str(avi), "--fixed-fps", str(FPS), "main.tscn", "--",
               f"--pack={Path(pack_dir).resolve()}", f"--timeline={timeline_file}"]
        start = time.monotonic()
        try:
            done = rig_v1._run(cmd, timeout_s, env)
        except subprocess.TimeoutExpired as exc:
            raise RenderError("generic rig render timed out") from exc
        render_s = time.monotonic() - start
        if done.returncode or not avi.is_file():
            raise RenderError(f"generic rig Godot failed ({done.returncode}): {(done.stderr or done.stdout)[-400:]}")
        start = time.monotonic()
        try:
            done = rig_v1._run([self.ffmpeg, "-v", "error", "-y", "-i", str(avi), "-frames:v", str(timeline["total_frames"]), "-c:v", "libx264", "-crf", "28",
                                "-preset", "medium", "-pix_fmt", "yuv420p", "-an", str(mp4)], timeout_s, env)
        except subprocess.TimeoutExpired as exc:
            raise RenderError("generic rig encoding timed out") from exc
        if done.returncode or not mp4.is_file():
            raise RenderError(f"generic rig encoding failed ({done.returncode})")
        return RenderResult(mp4, round(render_s, 2), round(time.monotonic() - start, 2), timeline["total_frames"], WIDTH, HEIGHT, FPS)
