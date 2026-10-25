"""Reproducible, paid-API-free 24-second technical preview of three cutout characters.

The preview is silent and uses developer-drawn placeholder art. It is not an
artistic-quality or audio-sync benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageChops

from . import demo_rig_v2, quality, rig_v2


def _visual_events(video: Path, filter_name: str) -> str:
    checked = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vf", filter_name,
         "-an", "-f", "null", os.devnull], capture_output=True, text=True, timeout=90, check=True,
    )
    return checked.stderr


def _frame(video: Path, seconds: float) -> Image.Image:
    extracted = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(video), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "pipe:1"], capture_output=True, timeout=30, check=True,
    )
    return Image.open(io.BytesIO(extracted.stdout)).convert("RGB")


def _changed_pixels(video: Path, first_s: float, second_s: float) -> int:
    difference = ImageChops.difference(_frame(video, first_s), _frame(video, second_s)).convert("L")
    return difference.point(lambda value: 255 if value > 5 else 0).histogram()[255]


def run(out: Path, godot: str, launcher: tuple[str, ...] = ()) -> dict:
    out = Path(out)
    timeline_file, pack = demo_rig_v2.create(out, frames_per_shot=192)
    timeline = json.loads(timeline_file.read_text(encoding="utf-8"))
    result = rig_v2.RigV2Renderer(godot, launcher=launcher).render(timeline, pack, out / "render", timeout_s=900)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=width,height,avg_frame_rate,codec_type,nb_frames", "-of", "json", str(result.video_path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    measured = json.loads(probe.stdout)
    streams = [s for s in measured["streams"] if s.get("codec_type") == "video"]
    video = streams[0] if streams else {}
    duration = float(measured["format"]["duration"])
    expected = timeline["total_frames"] / rig_v2.FPS
    if (not streams or video.get("width") != rig_v2.WIDTH or video.get("height") != rig_v2.HEIGHT
            or video.get("avg_frame_rate") != "24/1" or video.get("nb_frames") != str(timeline["total_frames"])
            or abs(duration - expected) > 0.01):
        raise RuntimeError("generic rig MP4 failed frame/duration QC")
    black = quality.parse_blackdetect(_visual_events(result.video_path, "blackdetect=d=0.5:pix_th=0.1"))
    freeze = quality.parse_freezedetect(_visual_events(result.video_path, "freezedetect=n=-60dB:d=1"))
    camera_change = _changed_pixels(result.video_path, 10.0, 14.0)
    walk_change = _changed_pixels(result.video_path, 17.0, 17.25)
    if camera_change < 1000 or walk_change < 100:
        raise RuntimeError("generic rig camera or walking action produced no measurable frame change")
    report = {
        "benchmark": "rig_v2_silent_three_character_technical_preview", "renderer_version": rig_v2.RigV2Renderer.version,
        "characters": timeline["characters"], "frames": result.frames, "fps": result.fps,
        "resolution": [result.width, result.height], "expected_duration_s": expected, "measured_duration_s": duration,
        "render_seconds": result.render_seconds, "encode_seconds": result.encode_seconds,
        "size_bytes": result.video_path.stat().st_size,
        "black_intervals_s": black, "freeze_intervals_s": freeze,
        "camera_changed_pixels": camera_change, "walking_changed_pixels": walk_change,
        "sha256": hashlib.sha256(result.video_path.read_bytes()).hexdigest(),
        "audio_sync_error_s": None, "peak_cpu_percent": None, "peak_memory_bytes": None,
        "audio_sync_note": "silent technical preview: no voice fixture or measured lip sync",
        "visual_review": "required: automated checks cannot establish artistic quality",
        "video": str(result.video_path.resolve()),
    }
    (out / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--godot", required=True)
    parser.add_argument("--launcher", nargs="*", default=[])
    args = parser.parse_args()
    print(json.dumps(run(args.out, args.godot, tuple(args.launcher)), indent=2))
