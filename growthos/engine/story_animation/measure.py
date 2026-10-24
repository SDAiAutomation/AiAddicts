"""Measure a rendered clip with ffprobe/ffmpeg and judge it with `quality.check_media` (IO module; not wired into the worker)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import quality


def _ffmpeg_text(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stderr


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate,duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s.get("codec_type") == "video")
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    num, den = video["r_frame_rate"].split("/")
    return {
        "video_duration_s": float(video.get("duration") or data["format"]["duration"]),
        "audio_duration_s": float(audio["duration"]) if audio and audio.get("duration") else None,
        "width": int(video["width"]), "height": int(video["height"]),
        "fps": float(num) / float(den), "size_bytes": Path(path).stat().st_size,
    }


def measure(path: Path) -> dict:
    report = probe(path)
    report["black"] = quality.parse_blackdetect(_ffmpeg_text(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.15:pix_th=0.04", "-an", "-f", "null", "-"]))
    report["freeze"] = quality.parse_freezedetect(_ffmpeg_text(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "freezedetect=n=-60dB:d=0.7", "-an", "-f", "null", "-"]))
    vol = _ffmpeg_text(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"])
    mean, peak = re.search(r"mean_volume:\s*(-?[\d.]+) dB", vol), re.search(r"max_volume:\s*(-?[\d.]+) dB", vol)
    if mean:
        report["mean_volume_db"] = float(mean.group(1))
    if peak:
        report["max_volume_db"] = float(peak.group(1))
    return report
