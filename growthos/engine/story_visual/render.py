"""Rendu MP4 vertical 1080x1920, H.264 + AAC, avec FFmpeg (argv en liste : aucune interpolation shell).

Cartes déjà composées (`overlay.compose_card`) + audio de narration positionné sur la timeline voix d'abord
(`timing.schedule`). Transitions sobres : cut, fondu enchaîné, fondu par le noir ; reframing optionnel très léger.
Chaque transition tient dans la pause de fin de scène : elle ne recouvre jamais la parole.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30
TRANSITION_S = {"cut": 0.0, "crossfade": 0.3, "fade": 0.3}
_XFADE = {"crossfade": "fade", "fade": "fadeblack"}
ZOOM = 0.05
TEXT_FADE_S = 0.15
PRESETS = ('ultrafast', 'veryfast', 'fast', 'medium')


class RenderError(RuntimeError):
    pass


def _timeout() -> float:
    try:
        return max(10.0, float(os.environ.get("STORY_RENDER_TIMEOUT_S", "") or 900))
    except ValueError:
        return 900.0


def _path(value) -> str:
    """Chemin ABSOLU d'un fichier existant : jamais une option (`-x`), une URL (`http:`), `concat:` ni `subfile,`."""
    path = Path(value).resolve()
    if not path.is_file():
        raise RenderError(f"input file not found: {path.name}")
    return str(path)


def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_timeout())
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"{cmd[0]} timed out") from exc
    if proc.returncode != 0:
        raise RenderError(f"{cmd[0]} failed: {proc.stderr[-800:]}")


def probe(path: str | Path) -> dict:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_range:format=duration",
             "-of", "json", _path(path)], capture_output=True, text=True, timeout=_timeout())
    except subprocess.TimeoutExpired as exc:
        raise RenderError("ffprobe timed out") from exc
    if proc.returncode != 0:
        raise RenderError(proc.stderr[-400:])
    data = json.loads(proc.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), {})
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), {})
    return {"duration": float(data["format"]["duration"]), "video": video, "audio": audio}


def audio_duration(path: str | Path) -> float:
    return probe(path)["duration"]


def _scene_clip(card: Path, duration: float, camera: str, out: Path, fps: int, preset: str) -> None:
    """Un plan = une carte fixe, avec un reframing optionnel ≤ 5 % (échelle variable dans le temps puis recadrage centré)."""
    # Les cartes JPEG sont en plage complète (pc) : sans conversion explicite, libx264 la garde et ffprobe annonce `yuvj420p`
    # (non standard pour TikTok/Shorts, lecteurs qui supposent la plage limitée => contraste faux). On force tv/BT.709.
    tv = f"scale={W}:{H}:out_range=tv:out_color_matrix=bt709"
    if camera == "still":
        vf = f"scale={W}:{H},{tv},format=yuv420p"
    else:
        z = f"(1+{ZOOM}*t/{duration:.3f})" if camera == "push_in" else f"(1+{ZOOM}-{ZOOM}*t/{duration:.3f})"
        vf = f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame:flags=bilinear,crop={W}:{H},{tv},format=yuv420p"
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-t", f"{duration:.3f}", "-i", str(card), "-vf", vf,
          "-r", str(fps), "-c:v", "libx264", "-preset", preset, "-crf", "20", "-colorspace", "bt709", "-color_range", "tv",
          "-an", str(out)])


def text_windows(slots: list[dict]) -> list[dict]:
    """Fenêtres du texte par scène (secondes de la timeline) : entrée à `start`, sortie TERMINÉE avant le début du fondu d'image
    sortant. Garantit qu'une légende a disparu avant que la suivante apparaisse (jamais deux légendes visibles ensemble)."""
    out = []
    for i, slot in enumerate(slots):
        last = i == len(slots) - 1
        t = 0.0 if last else TRANSITION_S[slot["transition"]]
        out.append({"in_start": slot["start"], "in_end": slot["start"] + TEXT_FADE_S,
                    "out_start": None if last else slot["end"] - t - TEXT_FADE_S, "out_end": None if last else slot["end"] - t})
    return out


def render_story(cards: list[str | Path], timeline: dict, audio_files: list[str | Path], out_path: str | Path,
                 work_dir: str | Path, *, fps: int = FPS, preset: str = "veryfast",
                 text_layers: list[str | Path | None] | None = None) -> dict:
    """`cards[i]`/`audio_files[i]` correspondent à `timeline['scenes'][i]`. Retourne la sonde du MP4 produit."""
    slots = timeline["scenes"]
    if not (len(cards) == len(audio_files) == len(slots)):
        raise ValueError("cards, audio files and timeline scenes must have the same length")
    for slot in slots:
        if slot.get("transition") not in TRANSITION_S or slot.get("camera") not in ("still", "push_in", "pull_out"):
            raise ValueError(f"invalid transition or camera for scene {slot.get('id')}")
    if not isinstance(fps, int) or not 8 <= fps <= 60 or preset not in PRESETS:
        raise ValueError("invalid fps or preset")
    if text_layers is not None and len(text_layers) != len(slots):
        raise ValueError("text_layers must have one entry (or None) per scene")
    layers = [None if t is None else _path(t) for t in (text_layers or [None] * len(slots))]
    cards = [_path(c) for c in cards]
    audio_files = [_path(a) for a in audio_files]
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    overlap = [0.0] + [TRANSITION_S[slots[i - 1]["transition"]] for i in range(1, len(slots))]
    clips = []
    for i, slot in enumerate(slots):
        clip = work / f"clip-{i:02d}.mp4"
        _scene_clip(Path(cards[i]), slot["duration"] + overlap[i], slot["camera"], clip, fps, preset)
        clips.append(clip)

    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    for audio in audio_files:
        inputs += ["-i", str(audio)]
    layer_inputs: dict[int, int] = {}
    for i, layer in enumerate(layers):
        if layer is not None:
            layer_inputs[i] = len(clips) + len(audio_files) + len(layer_inputs)
            window = slots[i]["end"] - slots[i]["start"]   # le calque n'est décodé que pendant sa scène
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{window:.3f}", "-i", layer]
    n = len(clips)
    graph = [f"[{i}:v]fps={fps},settb=AVTB,setpts=PTS-STARTPTS[n{i}]" for i in range(n)]
    label, length = "[n0]", slots[0]["duration"]
    for i in range(1, n):
        t, nxt = overlap[i], f"[v{i}]"
        if t > 0:
            graph.append(f"{label}[n{i}]xfade=transition={_XFADE[slots[i - 1]['transition']]}:duration={t}:offset={length - t:.3f}{nxt}")
        else:
            graph.append(f"{label}[n{i}]concat=n=2:v=1:a=0{nxt}")
        length += slots[i]["duration"]
        label = nxt
    # Texte : calque indépendant avec fondu séquencé. Il entre quand la scène est pleinement visible (fin du fondu entrant) et sort
    # AVANT le début du fondu sortant : les légendes de deux scènes ne sont jamais visibles ensemble.
    windows = text_windows(slots)
    for i, k in layer_inputs.items():
        slot = slots[i]
        chain = f"[{k}:v]format=rgba,fade=t=in:st=0:d={TEXT_FADE_S}:alpha=1"
        if i < n - 1:
            chain += f",fade=t=out:st={windows[i]['out_start'] - slot['start']:.3f}:d={TEXT_FADE_S}:alpha=1"
        graph.append(f"{chain},setpts=PTS+{slot['start']:.3f}/TB[t{i}]")
        graph.append(f"{label}[t{i}]overlay=0:0:eof_action=pass:format=auto[vt{i}]")
        label = f"[vt{i}]"
    for i, slot in enumerate(slots):
        ms = round(slot["audio_start"] * 1000)
        graph.append(f"[{n + i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    graph.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad[aout]")
    _run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(graph),
          "-map", label, "-map", "[aout]", "-t", f"{timeline['total_s']:.3f}",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", preset, "-crf", "20", "-r", str(fps),
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(Path(out_path).resolve())])
    return probe(out_path)
