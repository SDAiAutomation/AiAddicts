"""rig_v1 renderer: runs the packaged Godot project in a subprocess, then encodes with ffmpeg (not wired into the worker).

Security posture: the command is an argument list (no shell); the only inputs are a validated pack directory and a
timeline file written by us into a job-private directory; the Godot scene reads nothing else; secrets are stripped from the
child environment; the child has a hard timeout. Network isolation is applied by the runner through the launcher prefix (empty network namespace, unprivileged user), see the workflows.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import time
from pathlib import Path

from . import contract, packs
from .renderer import CostEstimate, RenderError, RenderResult

PROJECT_DIR = Path(__file__).parent / "godot" / "rig_v1"
WIDTH, HEIGHT, FPS = 1080, 1920, 24
# Wall-clock (render + encode) / video time. Measured once on a stock GitHub ubuntu-latest runner, software GL under xvfb,
# placeholder pack: 51.5 s render + 19.0 s encode for 21.6 s of video = 3.3 (workflow run 40115329358). One sample, placeholder
# art: kept at 4.0 for margin. Windows i3 laptop: 2.2 to 8.4 depending on machine load.
RENDER_RATIO_ESTIMATE = 4.0
_SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")


def clean_env(env: dict | None = None) -> dict:
    """Environment for child processes without anything that looks like a secret."""
    source = os.environ if env is None else env
    return {k: v for k, v in source.items() if not any(m in k.upper() for m in _SECRET_MARKERS)}


def confine(path: Path, root: Path) -> Path:
    """Resolved `path`, which must lie inside `root` (blocks traversal and symlink escapes)."""
    resolved, base = Path(path).resolve(), Path(root).resolve()
    if resolved != base and base not in resolved.parents:
        raise RenderError("path escapes the job directory")
    return resolved


def _run(cmd: list[str], timeout_s: float, env: dict) -> subprocess.CompletedProcess:
    """The single place that spawns a process (tests replace it)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env, check=False)
    except FileNotFoundError as exc:
        raise RenderError(f"executable not found: {Path(str(cmd[0])).name}") from exc


def _validate_timeline(timeline: dict) -> None:
    if not isinstance(timeline, dict):
        raise RenderError("timeline must be an object")
    for key in ("fps", "total", "lines", "subs", "shots"):
        if key not in timeline:
            raise RenderError(f"timeline.{key} is missing")
    total = timeline["total"]
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(total) or not 0 < total <= contract.ABSOLUTE_MAX_DURATION_S:
        raise RenderError("timeline.total must be positive and within the duration limit")
    if timeline["fps"] != FPS:
        raise RenderError(f"timeline.fps must be {FPS}")
    def number(value: object) -> bool:
        return type(value) in (int, float) and math.isfinite(value)

    def interval(item: object, label: str, *, positive: bool = False) -> tuple[float, float]:
        if not isinstance(item, dict) or not number(item.get("start")) or not number(item.get("end")):
            raise RenderError(f"{label} needs finite start and end")
        start, end = item["start"], item["end"]
        if start < 0 or end <= start or end > total + 0.05 or (positive and start >= total):
            raise RenderError(f"{label} is outside the timeline")
        return start, end

    roles = {"pip", "ros"}  # rig_v1 is a two-character pilot; a new rig must declare its own roster.
    backgrounds = set(packs.REQUIRED_SPRITES) & {"bg_alley", "bg_shop", "bg_street", "bg_cafe"}
    shots = timeline["shots"]
    if not isinstance(shots, list) or not shots or len(shots) > 200:
        raise RenderError("timeline.shots must contain 1-200 shots")
    previous_end = 0.0
    for index, shot in enumerate(shots):
        label = f"timeline.shots[{index}]"
        start, end = interval(shot, label, positive=True)
        if abs(start - previous_end) > 0.05:
            raise RenderError(f"{label} does not follow the previous shot")
        previous_end = end
        if not isinstance(shot.get("background"), str) or shot["background"] not in backgrounds:
            raise RenderError(f"{label}.background is not in the pack")
        camera = shot.get("camera")
        if not isinstance(camera, dict) or camera.get("move") not in contract.CAMERA_MOVES:
            raise RenderError(f"{label}.camera is invalid")
        if any(not number(camera.get(k)) or not 0.8 <= camera[k] <= 4.0 for k in ("zoom_from", "zoom_to")):
            raise RenderError(f"{label}.camera zoom is invalid")
        if shot.get("shot_type") not in contract.SHOT_TYPES or shot.get("transition_in") not in contract.TRANSITIONS:
            raise RenderError(f"{label} has an unsupported shot type or transition")
        speaker = shot.get("speaker")
        if speaker is not None and (not isinstance(speaker, str) or speaker not in roles | {"", "narrator"}):
            raise RenderError(f"{label}.speaker is not supported by rig_v1")
        actors = shot.get("actors")
        if not isinstance(actors, list) or len(actors) > 2:
            raise RenderError(f"{label}.actors must be a list of at most two")
        seen = set()
        for actor in actors:
            if not isinstance(actor, dict) or not isinstance(actor.get("role"), str) or actor["role"] not in roles or actor["role"] in seen:
                raise RenderError(f"{label}.actors has an unknown or repeated role")
            seen.add(actor["role"])
            if (actor.get("side") not in contract.SIDES or actor.get("facing") not in contract.FACINGS
                    or actor.get("mood") not in contract.MOODS or actor.get("gesture") not in contract.GESTURES
                    or not isinstance(actor.get("props"), list)):
                raise RenderError(f"{label}.actors has an unsupported instruction")
        if isinstance(speaker, str) and speaker in roles and speaker not in seen:
            raise RenderError(f"{label}.speaker is absent from the shot")
    if abs(previous_end - total) > 0.05:
        raise RenderError("timeline.shots do not cover timeline.total")
    for name in ("lines", "subs"):
        items = timeline[name]
        if not isinstance(items, list) or len(items) > 1000:
            raise RenderError(f"timeline.{name} must be a bounded list")
        for index, item in enumerate(items):
            label = f"timeline.{name}[{index}]"
            interval(item, label)
            if name == "lines":
                if not isinstance(item.get("who"), str) or item["who"] not in roles | {"narrator"} or not isinstance(item.get("mouth"), str) or not item["mouth"] or set(item["mouth"]) - {"c", "o", "r"}:
                    raise RenderError(f"{label} has an unsupported role or mouth cue")
            elif not isinstance(item.get("text"), str) or len(item["text"]) > 500:
                raise RenderError(f"{label}.text is invalid")


class RigV1Renderer:
    name = "rig_v1"
    version = "1"

    def __init__(self, godot_bin: str, launcher: tuple = (), ffmpeg: str = "ffmpeg", project_dir: Path = PROJECT_DIR):
        self.godot_bin = godot_bin
        self.launcher = tuple(launcher)  # e.g. ("xvfb-run", "-a") on a headless Linux runner
        self.ffmpeg = ffmpeg
        self.project_dir = Path(project_dir)

    def estimate(self, total_seconds: float, tts_chars: int) -> CostEstimate:
        if not math.isfinite(total_seconds) or total_seconds <= 0 or tts_chars < 0:
            raise ValueError("total_seconds must be positive and tts_chars non-negative")
        return CostEstimate(render_seconds=round(total_seconds * RENDER_RATIO_ESTIMATE, 1), tts_chars=int(tts_chars), provider_calls=0)

    def godot_command(self, avi: Path, pack_dir: Path, timeline_file: Path) -> list[str]:
        return [
            *self.launcher, self.godot_bin, "--path", str(self.project_dir), "--rendering-driver", "opengl3",
            "--write-movie", str(avi), "--fixed-fps", str(FPS), "main.tscn", "--",
            f"--pack={pack_dir}", f"--timeline={timeline_file}",
        ]

    def render(self, timeline: dict, pack_dir: Path, workdir: Path, timeout_s: float = 600.0) -> RenderResult:
        _validate_timeline(timeline)
        problems = packs.validate_pack(pack_dir)
        if problems:
            raise RenderError("pack is not usable: " + "; ".join(problems[:5]))
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        timeline_file = confine(workdir / "timeline.json", workdir)
        timeline_file.write_text(json.dumps(timeline, ensure_ascii=False), encoding="utf-8")
        avi, mp4 = confine(workdir / "silent.avi", workdir), confine(workdir / "silent.mp4", workdir)
        env = clean_env()

        t0 = time.monotonic()
        try:
            done = _run(self.godot_command(avi, Path(pack_dir).resolve(), timeline_file), timeout_s, env)
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"render exceeded the {timeout_s:.0f}s limit") from exc
        render_s = time.monotonic() - t0
        if done.returncode != 0 or not avi.is_file():
            tail = (done.stderr or done.stdout or "")[-300:].replace("\n", " ")
            raise RenderError(f"renderer failed with exit code {done.returncode}: {tail}")

        t1 = time.monotonic()
        enc = ["-v", "error", "-y", "-i", str(avi), "-c:v", "libx264", "-crf", "28", "-preset", "medium", "-pix_fmt", "yuv420p", "-an", str(mp4)]
        try:
            done = _run([self.ffmpeg, *enc], timeout_s, env)
        except subprocess.TimeoutExpired as exc:
            raise RenderError("encoding exceeded the time limit") from exc
        if done.returncode != 0 or not mp4.is_file():
            raise RenderError(f"encoding failed with exit code {done.returncode}")
        frames = int(math.ceil(timeline["total"] * FPS))
        return RenderResult(mp4, round(render_s, 2), round(time.monotonic() - t1, 2), frames, WIDTH, HEIGHT, FPS)
