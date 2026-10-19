"""Render deterministic, voice-free quiz frames for visual review.

This exercises the production libass overlay renderer, not the voice-synced
assembler. Durations and the caption are illustrative; do not use these frames
as evidence of audio or effect synchronization.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.captions import write_ass
from engine.quiz import QUIZ_THEMES, compile_quiz


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolution", default="720x1280", choices=["720x1280", "1280x720"])
    args = parser.parse_args()
    output = ROOT / "output" / "quiz-theme-audit" / args.resolution
    output.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    source["quiz"]["questions"][0]["choices"].append("La Terre")
    width, height = (int(value) for value in args.resolution.split("x"))
    thumb_width = 180 if width < height else 320
    thumb_height = round(thumb_width * height / width)
    rows = []
    for theme in sorted(QUIZ_THEMES):
        row = []
        for presentation in ("classic", "motion"):
            script = json.loads(json.dumps(source))
            script["quiz"].update({"theme": theme, "presentation": presentation})
            blocks = compile_quiz(script)["blocks"][1:3]
            for block in blocks:
                block["quiz_visual_available"] = False
            folder = output / f"{theme}-{presentation}"
            folder.mkdir(exist_ok=True)
            write_ass([], str(folder / "overlay.ass"), "bold_stroke", args.resolution,
                      blocks=blocks, block_durations=[7, 3])
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", f"color=c=0x080e1c:s={args.resolution}:r=1:d=10",
                            "-vf", r"subtitles=overlay.ass,select=eq(n\,2)+eq(n\,8)",
                            "-fps_mode", "passthrough", "frame-%02d.png"], cwd=folder, check=True)
            row.extend([folder / "frame-01.png", folder / "frame-02.png"])
        rows.append((theme, row))
    margin, label_height = 12, 28
    sheet = Image.new("RGB", (4 * thumb_width + 5 * margin,
                              len(rows) * (thumb_height + label_height + margin) + margin), "#f4f3ef")
    draw = ImageDraw.Draw(sheet)
    for row_index, (theme, frames) in enumerate(rows):
        y = margin + row_index * (thumb_height + label_height + margin)
        draw.text((margin, y), f"{theme} | classic Q/R | motion Q/R", fill="#111111")
        for column, frame in enumerate(frames):
            with Image.open(frame) as image:
                image.thumbnail((thumb_width, thumb_height))
                sheet.paste(image.convert("RGB"), (margin + column * (thumb_width + margin), y + label_height))
    destination = output / "contact-sheet.jpg"
    sheet.save(destination, quality=90)
    print(destination)


if __name__ == "__main__":
    main()
