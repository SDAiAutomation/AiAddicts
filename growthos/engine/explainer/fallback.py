"""Repli d'un plan en échec : la scène `motion_graphics` Pillow équivalente (carte de texte), jamais silencieux.

Le pipeline écrit le plan, la raison et le texte affiché dans `explainer.report.json` (section `fallbacks`). Le clip est
normalisé (taille, fréquence d'images, format de pixels) pour pouvoir être recollé aux segments rendus par Chromium.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FPS = 30
MAX_CHARS = 70


def pillow_clip(text: str, duration: float, out_path: str | Path, resolution: str = "1080x1920") -> str:
    from engine.motion_graphics import render_scene_clip, resolve_scene

    shown = (text.strip()[:MAX_CHARS]).rstrip()
    raw = Path(out_path).with_suffix(".raw.mp4")
    scene = resolve_scene({"sceneType": "icon_text", "displayText": shown}, shown)
    render_scene_clip(scene, duration, str(raw), resolution=resolution, fps=FPS)
    width, height = resolution.split("x")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-vf", f"fps={FPS},scale={width}:{height},format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out_path)], check=True)
    raw.unlink(missing_ok=True)
    return str(out_path)
