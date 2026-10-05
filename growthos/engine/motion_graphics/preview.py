"""Preview one frame or a contact sheet without encoding a video."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw

from engine import visuals
from . import renderer
from .theme import resolve_theme


def render_preview(scene: dict, times: list[float], duration: float, out: Path,
                   resolution: str, theme_overrides: dict | None = None) -> Path:
    """Use the production frame renderer; multiple times become one contact sheet."""
    if duration <= 0 or not times or any(not 0 <= t <= duration for t in times):
        raise ValueError("preview times must be between zero and duration")
    size = tuple(int(v) for v in resolution.split("x"))
    if len(times) == 1:
        renderer.render_still(scene, times[0], duration, str(out), resolution, theme_overrides)
        return out
    thumb_width = min(size[0], 360)
    thumb_height = round(size[1] * thumb_width / size[0])
    margin, label_height = 16, 28
    sheet = Image.new("RGB", (len(times) * (thumb_width + margin) + margin,
                              thumb_height + label_height + margin * 2), "#171717")
    draw = ImageDraw.Draw(sheet)
    theme = resolve_theme(theme_overrides)
    for index, at in enumerate(times):
        frame = renderer.render_frame(scene, at / duration, size, theme)
        frame.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = margin + index * (thumb_width + margin)
        sheet.paste(frame, (x, margin + label_height))
        draw.text((x, margin + 5), f"{at:g} s", fill="white")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview motion graphics frames without encoding a video")
    parser.add_argument("scene", type=Path, help="JSON scene or script containing blocks")
    parser.add_argument("--block", type=int, default=1, help="1-based block number for a script JSON")
    parser.add_argument("--at", required=True, help="one or comma-separated seconds into the block, e.g. 0,1,2.5")
    parser.add_argument("--duration", type=float, required=True, help="block duration in seconds")
    parser.add_argument("--words", type=Path, help="existing block-NN.words.json for voice synchronization")
    parser.add_argument("--out", type=Path, required=True, help="output PNG path")
    parser.add_argument("--resolution", default="1080x1920")
    args = parser.parse_args()
    times = [float(value.strip()) for value in args.at.split(",")]
    source = json.loads(args.scene.read_text(encoding="utf-8"))
    if isinstance(source, dict) and isinstance(source.get("blocks"), list):
        if not 1 <= args.block <= len(source["blocks"]):
            parser.error("--block is outside the script's blocks")
        block = source["blocks"][args.block - 1]
        theme = source.get("motion_graphics_theme")
    else:
        block, theme = {"motion_graphic": source, "text": ""}, None
    words_path = args.words or Path("__no_words_file__")
    scene = visuals.prepare_motion_graphics_scene(
        block, args.duration, words_path, tuple(int(v) for v in args.resolution.split("x")),
        theme, args.block - 1,
    )
    print(render_preview(scene, times, args.duration, args.out, args.resolution, theme))


if __name__ == "__main__":
    main()
