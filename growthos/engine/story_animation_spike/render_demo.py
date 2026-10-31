"""Offline 2D cartoon renderer experiment; no cloud APIs or production integration.

Requires Pillow and ffmpeg on PATH. Generates a silent vertical MP4 with
procedural characters, moving arms, blinking and dialogue-driven mouth motion.
Mouth motion is NOT phoneme-based lip sync. All artwork is original.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from .timeline import build_timeline, frame_state

WIDTH, HEIGHT, FPS = 540, 960, 24

DEMO = {
    "characters": [{"id": "neo"}, {"id": "orion"}],
    "shots": [
        {"id": "s1", "speaker_id": "neo", "duration_s": 3, "action": "talk"},
        {"id": "s2", "speaker_id": "orion", "duration_s": 3.5, "action": "gesture"},
        {"id": "s3", "speaker_id": "neo", "duration_s": 3, "action": "react", "emotion": "happy"},
    ],
}
LINES = {
    "s1": "Orion, comment savoir si une idée est vraiment la mienne ?",
    "s2": "Pose-toi une question : qui gagne si tu y crois ?",
    "s3": "Alors, je vais apprendre à réfléchir par moi-même.",
}


def _actor(draw: ImageDraw.ImageDraw, name: str, x: float, y: float, t: float, speaking: bool) -> None:
    fox = name == "neo"
    main = (228, 113, 55) if fox else (113, 128, 173)
    light = (253, 214, 155) if fox else (197, 208, 224)
    ink = (33, 42, 63)
    y += math.sin(t * 5) * 5
    # legs, body, animated arms
    for sign in (-1, 1):
        draw.line([(x + sign * 25, y + 125), (x + sign * (31 + math.sin(t * 5) * 7), y + 184)], fill=ink, width=17)
    draw.ellipse((x - 62, y - 15, x + 62, y + 145), fill=main, outline=ink, width=5)
    draw.ellipse((x - 32, y + 25, x + 32, y + 117), fill=light)
    for sign in (-1, 1):
        gesture = math.sin(t * 6 + sign) * (24 if speaking else 6)
        draw.line([(x + sign * 51, y + 40), (x + sign * 92, y + 80 + gesture)], fill=main, width=23)
        draw.ellipse((x + sign * 92 - 13, y + 80 + gesture - 13,
                      x + sign * 92 + 13, y + 80 + gesture + 13), fill=light)
    hy = y - 89 + (math.sin(t * 3) * 5 if speaking else 0)
    if fox:
        for sign in (-1, 1):
            draw.polygon([(x + sign * 62, hy - 31), (x + sign * 63, hy - 124),
                          (x + sign * 12, hy - 66)], fill=main)
    else:
        for sign in (-1, 1):
            draw.ellipse((x + sign * 45 - 26, hy - 81, x + sign * 45 + 26, hy - 25), fill=main)
    draw.ellipse((x - 76, hy - 83, x + 76, hy + 63), fill=main, outline=ink, width=5)
    draw.ellipse((x - 58, hy - 10, x + 58, hy + 54), fill=light)
    blink = abs((t * 0.5) % 3.7 - 1.85) < 0.055
    for dx in (-27, 27):
        if blink:
            draw.line([(x + dx - 10, hy - 20), (x + dx + 10, hy - 20)], fill=ink, width=5)
        else:
            draw.ellipse((x + dx - 10, hy - 30, x + dx + 10, hy - 6), fill="white")
            draw.ellipse((x + dx - 4, hy - 23, x + dx + 5, hy - 9), fill=ink)
    if fox:
        draw.polygon([(x - 12, hy + 8), (x + 12, hy + 8), (x, hy + 20)], fill=ink)
    else:
        draw.polygon([(x - 13, hy + 3), (x + 13, hy + 3), (x, hy + 24)], fill=(237, 171, 73))
    if speaking and math.sin(t * 17) > -0.1:
        draw.ellipse((x - 15, hy + 29, x + 15, hy + 47), fill=(105, 43, 60), outline=ink, width=2)
    else:
        draw.arc((x - 16, hy + 24, x + 16, hy + 41), 0, 180, fill=ink, width=3)


def draw_frame(plan: dict, time_ms: int) -> Image.Image:
    timeline = build_timeline(plan)
    state = frame_state(timeline, time_ms)
    t = time_ms / 1000
    image = Image.new("RGB", (WIDTH, HEIGHT), (25, 35, 64))
    draw = ImageDraw.Draw(image)
    draw.ellipse((-120, -140, 660, 600), fill=(39, 57, 91))
    draw.ellipse((50, 80, 180, 210), fill=(239, 206, 137))
    draw.rectangle((0, 630, WIDTH, HEIGHT), fill=(41, 79, 79))
    draw.ellipse((-80, 580, 620, 760), fill=(55, 100, 94))
    pan = math.sin(t * 0.6) * 5
    _actor(draw, "neo", 170 + pan, 470, t, state["speaker_id"] == "neo")
    _actor(draw, "orion", 390 + pan, 465, t + 0.4, state["speaker_id"] == "orion")
    draw.rounded_rectangle((18, 28, 522, 102), radius=18, fill=(15, 22, 43))
    draw.text((35, 44), "STORY STUDIO / OFFLINE PROTOTYPE", fill=(237, 225, 194))
    draw.rounded_rectangle((22, 736, 518, 923), radius=24, fill=(12, 19, 37))
    draw.text((42, 755), state["speaker_id"].upper(), fill=(253, 198, 102))
    dialogue = LINES.get(state["shot_id"], "")
    words, lines, current = dialogue.split(), [], ""
    for word in words:
        if len(current + " " + word) > 38:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    for i, line in enumerate(lines):
        draw.text((42, 801 + i * 27), line, fill="white")
    draw.rounded_rectangle((22, 934, 518, 942), radius=4, fill=(70, 88, 101))
    draw.rounded_rectangle((22, 934, 22 + 496 * time_ms / timeline[-1].end_ms, 942),
                           radius=4, fill=(247, 186, 89))
    return image


def render_demo(output: str | Path, fps: int = FPS) -> Path:
    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 60:
        raise ValueError("invalid fps")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    timeline = build_timeline(DEMO)
    frames = round(timeline[-1].end_ms * fps / 1000)
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps),
               "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "25", "-pix_fmt", "yuv420p", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for n in range(frames):
            process.stdin.write(draw_frame(DEMO, round(n * 1000 / fps)).tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return output


if __name__ == "__main__":
    print(render_demo(Path("neo_orion_offline.mp4")))
