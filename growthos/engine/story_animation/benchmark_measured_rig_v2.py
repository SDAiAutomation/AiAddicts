"""Offline render proof for the existing measured timeline and generic Godot rig.

The fixture contains measured timing but no voice recording. The MP4 is silent;
this checks frame alignment and subtitles, not audio synchronization quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from . import demo_rig_v2, rig_v2, rig_v2_compile

FIXTURE = Path(__file__).parent / "fixtures" / "prototype_timeline.json"


def run(out: Path, godot: str, launcher: tuple[str, ...] = ()) -> dict:
    out = Path(out)
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _, pack = demo_rig_v2.create(out, frames_per_shot=12)
    timeline = rig_v2_compile.compile_measured(source, source["shots"], {"pip": "pip", "ros": "rosette"})
    rig_v2.validate_timeline(timeline, pack)
    (out / "compiled_timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    result = rig_v2.RigV2Renderer(godot, launcher=launcher).render(timeline, pack, out / "render", timeout_s=900)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=width,height,avg_frame_rate,codec_type,nb_frames", "-of", "json", str(result.video_path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    measured = json.loads(probe.stdout)
    video = next((s for s in measured["streams"] if s.get("codec_type") == "video"), {})
    duration = float(measured["format"]["duration"])
    if (video.get("nb_frames") != str(timeline["total_frames"]) or video.get("width") != rig_v2.WIDTH
            or video.get("height") != rig_v2.HEIGHT or video.get("avg_frame_rate") != "24/1"
            or abs(duration - source["total"]) >= 1 / rig_v2.FPS
            or timeline["total_frames"] != math.ceil(source["total"] * rig_v2.FPS)):
        raise RuntimeError("measured timeline MP4 failed frame or duration QC")
    report = {
        "benchmark": "rig_v2_existing_measured_timeline_silent_preview",
        "measured_source_duration_s": source["total"], "video_duration_s": duration,
        "duration_error_s": round(duration - source["total"], 6),
        "frames": result.frames, "fps": result.fps, "resolution": [result.width, result.height],
        "shots": len(timeline["shots"]), "subtitles": len(timeline["subs"]),
        "render_seconds": result.render_seconds, "encode_seconds": result.encode_seconds,
        "size_bytes": result.video_path.stat().st_size,
        "sha256": hashlib.sha256(result.video_path.read_bytes()).hexdigest(),
        "audio_sync_error_s": None,
        "audio_sync_note": "No licensed voice recording in the measured fixture; output is silent.",
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
