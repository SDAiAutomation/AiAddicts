"""Offline quality preview: python creative_quality_cli.py script.json [--video clip.mp4].

Reads existing artifacts and prints JSON; does not modify generation or publishing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.creative_quality import analyze
from engine.render_preflight import inspect_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Faceloop quality shadow-mode preview")
    parser.add_argument("script", type=Path)
    parser.add_argument("--video", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    script = json.loads(args.script.read_text(encoding="utf-8"))
    if not isinstance(script, dict):
        parser.error("Script JSON must be an object")
    report = {"script": analyze(script)}
    if args.video is not None:
        report["render"] = inspect_video(args.video)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
