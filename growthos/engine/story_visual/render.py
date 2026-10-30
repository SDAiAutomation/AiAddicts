"""Rendu MP4 vertical 1080x1920, H.264 + AAC, avec FFmpeg (argv en liste : aucune interpolation shell).

Cartes déjà composées (`overlay.compose_card`) + audio de narration positionné sur la timeline voix d'abord
(`timing.schedule`). Transitions sobres : cut, fondu enchaîné, fondu par le noir ; reframing optionnel très léger.
Chaque transition tient dans la pause de fin de scène : elle ne recouvre jamais la parole.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30
TRANSITION_S = {"cut": 0.0, "crossfade": 0.3, "fade": 0.3}
_XFADE = {"crossfade": "fade", "fade": "fadeblack"}
ZOOM = 0.05


class RenderError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(f"{cmd[0]} failed: {proc.stderr[-800:]}")


def probe(path: str | Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(proc.stderr[-400:])
    data = json.loads(proc.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {"duration": float(data["format"]["duration"]), "video": video, "audio": audio}


def audio_duration(path: str | Path) -> float:
    return probe(path)["duration"]


def _scene_clip(card: Path, duration: float, camera: str, out: Path) -> None:
    frames = max(2, round(duration * FPS))
    if camera == "still":
        vf = f"scale={W}:{H},format=yuv420p"
        cmd_in = ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(card)]
    else:
        z = f"1+{ZOOM}*on/{frames}" if camera == "push_in" else f"1+{ZOOM}-{ZOOM}*on/{frames}"
        vf = (f"scale={W * 3 // 2}:{H * 3 // 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
        cmd_in = ["-i", str(card)]
    _run(["ffmpeg", "-y", "-v", "error", *cmd_in, "-vf", vf, "-frames:v", str(frames), "-r", str(FPS),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)])


def render_story(cards: list[str | Path], timeline: dict, audio_files: list[str | Path], out_path: str | Path,
                 work_dir: str | Path) -> dict:
    """`cards[i]`/`audio_files[i]` correspondent à `timeline['scenes'][i]`. Retourne la sonde du MP4 produit."""
    slots = timeline["scenes"]
    if not (len(cards) == len(audio_files) == len(slots)):
        raise ValueError("cards, audio files and timeline scenes must have the same length")
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    overlap = [0.0] + [TRANSITION_S[slots[i - 1]["transition"]] for i in range(1, len(slots))]
    clips = []
    for i, slot in enumerate(slots):
        clip = work / f"clip-{i:02d}.mp4"
        _scene_clip(Path(cards[i]), slot["duration"] + overlap[i], slot["camera"], clip)
        clips.append(clip)

    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    for audio in audio_files:
        inputs += ["-i", str(audio)]
    n = len(clips)
    graph = [f"[{i}:v]fps={FPS},settb=AVTB,setpts=PTS-STARTPTS[n{i}]" for i in range(n)]
    label, length = "[n0]", slots[0]["duration"]
    for i in range(1, n):
        t, nxt = overlap[i], f"[v{i}]"
        if t > 0:
            graph.append(f"{label}[n{i}]xfade=transition={_XFADE[slots[i - 1]['transition']]}:duration={t}:offset={length - t:.3f}{nxt}")
        else:
            graph.append(f"{label}[n{i}]concat=n=2:v=1:a=0{nxt}")
        length += slots[i]["duration"]
        label = nxt
    for i, slot in enumerate(slots):
        ms = round(slot["audio_start"] * 1000)
        graph.append(f"[{n + i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    graph.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad[aout]")
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph),
          "-map", label, "-map", "[aout]", "-t", f"{timeline['total_s']:.3f}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)])
    return probe(out_path)
