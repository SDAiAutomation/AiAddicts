"""Local command line for the rig_v1 renderer (developer tool, not wired into the worker).

  python -m growthos.engine.story_animation.cli placeholder-pack --out DIR
  python -m growthos.engine.story_animation.cli render --timeline FILE --pack DIR --out CLIP.mp4 --godot GODOT [--audio MIX.wav] [--launcher "xvfb-run -a"]
Prints one JSON object (timings, measurements, quality problems). Exit codes: 0 pass, 2 the render failed, 3 the clip needs review.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from . import measure, packs, quality
from .renderer import RenderError
from .rig_v1 import FPS, HEIGHT, WIDTH, RigV1Renderer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="story_animation", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    pp = sub.add_parser("placeholder-pack", help="write a synthetic pack with the right sprite sizes")
    pp.add_argument("--out", required=True)
    r = sub.add_parser("render", help="render a timeline with a pack")
    r.add_argument("--timeline", required=True)
    r.add_argument("--pack", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--godot", required=True)
    r.add_argument("--audio")
    r.add_argument("--launcher", default="")
    r.add_argument("--timeout", type=float, default=900.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "placeholder-pack":
        packs.write_placeholder_pack(Path(args.out))
        print(json.dumps({"pack": args.out, "files": len(packs.REQUIRED_SPRITES), "problems": packs.validate_pack(Path(args.out))}))
        return 0
    timeline = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    renderer = RigV1Renderer(args.godot, launcher=tuple(shlex.split(args.launcher)))
    with tempfile.TemporaryDirectory(prefix="story_anim_") as tmp:
        try:
            result = renderer.render(timeline, Path(args.pack), Path(tmp), args.timeout)
        except RenderError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 2
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        if args.audio:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(result.video_path), "-i", args.audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                   "-af", "apad", "-t", str(timeline["total"]), str(out)]
        else:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(result.video_path), "-c", "copy", str(out)]
        subprocess.run(cmd, check=True)
    report = measure.measure(out)
    if report.get("audio_duration_s") is None:
        report["audio_duration_s"] = report["video_duration_s"]  # silent benchmark clip: nothing to compare
    problems = quality.check_media(report, {"width": WIDTH, "height": HEIGHT, "fps": FPS})
    summary = {
        "ok": not problems, "renderer": renderer.name, "version": renderer.version,
        "render_seconds": result.render_seconds, "encode_seconds": result.encode_seconds,
        "video_seconds": report["video_duration_s"], "render_ratio": round(result.render_seconds / max(report["video_duration_s"], 0.001), 2),
        "size_mib": round(report["size_bytes"] / 1048576, 2), "problems": problems,
    }
    print(json.dumps(summary))
    return 0 if not problems else 3


if __name__ == "__main__":
    sys.exit(main())
