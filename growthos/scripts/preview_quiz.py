"""Render a local quiz layout preview without paid generation or publication.

Run: python scripts/preview_quiz.py --theme studio
Timing is illustrative; the preview has no voiceover.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.captions import write_ass
from engine.quiz import QUIZ_THEMES, compile_quiz


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=sorted(QUIZ_THEMES), default="studio")
    parser.add_argument("--resolution", choices=["1080x1920", "720x1280", "1080x1080", "1920x1080"], default="1080x1920")
    args = parser.parse_args()
    output = ROOT / "output" / "quiz-preview" / f"{args.theme}-{args.resolution}"
    output.mkdir(parents=True, exist_ok=True)
    script = json.loads((ROOT / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    script["quiz"]["theme"] = args.theme
    # Four choices exercise the most crowded supported layout.
    script["quiz"]["questions"][0]["choices"].append("La Terre")
    blocks = compile_quiz(script)["blocks"]
    blocks = [block for block in blocks if block["quiz_phase"] in {"question", "reveal"}]
    for block in blocks:
        block["quiz_visual_available"] = False
    durations = [7.0 if block["quiz_phase"] == "question" else 3.0 for block in blocks]
    cues = []
    cursor = 0.0
    for block, duration in zip(blocks, durations):
        if block["quiz_phase"] == "reveal":
            # Representative explanation caption, independent of provider timing.
            cues.append({"start": cursor + 0.3, "end": cursor + 2.8,
                         "text": "Tu avais trouvé ?", "words": []})
        cursor += duration
    write_ass(cues, str(output / "preview.ass"), "bold_stroke", args.resolution,
              blocks=blocks, block_durations=durations)
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x070C17:s={args.resolution}:r=25:d={cursor}",
        "-vf", "subtitles=preview.ass", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "preview.mp4",
    ], cwd=output, check=True)
    for label, seconds in (("question", 2), ("countdown", 5), ("answer", 8)):
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds),
            "-i", "preview.mp4", "-frames:v", "1", f"{label}.png",
        ], cwd=output, check=True)
    print(output / "preview.mp4")


if __name__ == "__main__":
    main()
