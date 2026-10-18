"""Mesure le poids et le temps de rendu de la mise en scène Motion d'un quiz long.

Run: python scripts/measure_quiz_motion.py [--questions 25] [--resolution 1920x1080] [--presentation motion] [--render]

Sans voix : durées illustratives (question 12 s dont 5 s de réflexion, révélation 6 s). Le temps FFmpeg
mesuré sur cette machine n'est qu'un ordre de grandeur : à refaire sur le worker de production.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.captions import _quiz_events, write_ass
from engine import quiz_motion
from engine.quiz import compile_quiz


def long_quiz(count: int, presentation: str) -> dict:
    script = json.loads((ROOT / "content/scripts/exemple-quiz.json").read_text(encoding="utf-8"))
    subjects = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet"]
    script["quiz"].update({"recipe": "long", "presentation": presentation, "illustrations": False})
    script["quiz"]["questions"] = [
        {"question": f"Which {subjects[i % 10]} concept number {i} appears in lesson {i * 7}?",
         "choices": [f"Answer {i} first", f"Answer {i} second", f"Answer {i} third", f"Answer {i} fourth"],
         "correct_choice": i % 4, "explanation": f"Explanation for {i}.", "fact": f"fact {i}"}
        for i in range(count)
    ]
    return script


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=25)
    parser.add_argument("--resolution", default="1920x1080")
    parser.add_argument("--presentation", choices=["classic", "motion"], default="motion")
    parser.add_argument("--render", action="store_true", help="Mesure aussi le temps FFmpeg (fond uni + sous-titres)")
    parser.add_argument("--full-screen-rect", action="store_true", help="Ancien rendu : scène Motion dessinée en rectangle plein écran par libass")
    args = parser.parse_args()
    width, height = (int(v) for v in args.resolution.split("x"))
    script = long_quiz(args.questions, args.presentation)
    blocks = compile_quiz(script)["blocks"]
    base = None if args.full_screen_rect else quiz_motion.base_background_for(script, 0.0)
    for block in blocks:
        block["quiz_visual_available"] = False
        if base:
            block["quiz_base_background"] = "#" + base[2:].lower()
    durations = [{"question": 12.0, "reveal": 6.0}.get(block["quiz_phase"], 3.0) for block in blocks]
    for block, duration in zip(blocks, durations):
        if block["quiz_phase"] == "question":
            block["hold_after_seconds"] = 5
    total = sum(durations)
    started = time.perf_counter()
    events = _quiz_events(blocks, durations, width, height)
    build = time.perf_counter() - started
    print(f"{args.presentation} {args.resolution} : {len(events)} événements, "
          f"{sum(len(e) for e in events) / 1024:.0f} Ko d'événements, {total:.0f} s de vidéo, "
          f"construits en {build * 1000:.0f} ms")
    if args.render:
        with tempfile.TemporaryDirectory() as folder:
            write_ass([], str(Path(folder) / "q.ass"), "bold_stroke", args.resolution, blocks=blocks, block_durations=durations)
            size = (Path(folder) / "q.ass").stat().st_size / 1024
            started = time.perf_counter()
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"color=c={base or '0x0F172A'}:s={args.resolution}:r=25:d={total}", "-vf", "subtitles=q.ass",
                            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "q.mp4"],
                           cwd=folder, check=True)
            elapsed = time.perf_counter() - started
            print(f"fichier .ass : {size:.0f} Ko ; rendu FFmpeg : {elapsed:.0f} s ({total / elapsed:.1f}x temps réel)")


if __name__ == "__main__":
    main()
