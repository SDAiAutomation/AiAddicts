"""Reproducible, paid-API-free 24-second technical preview of three cutout characters.

The preview is silent and uses developer-drawn placeholder art. It is not an
artistic-quality or audio-sync benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from . import demo_rig_v2, rig_v2


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
    report = {
        "benchmark": "rig_v2_silent_three_character_technical_preview", "renderer_version": rig_v2.RigV2Renderer.version,
        "characters": timeline["characters"], "frames": result.frames, "fps": result.fps,
        "resolution": [result.width, result.height], "expected_duration_s": expected, "measured_duration_s": duration,
        "render_seconds": result.render_seconds, "encode_seconds": result.encode_seconds,
        "size_bytes": result.video_path.stat().st_size,
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
