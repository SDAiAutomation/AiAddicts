"""Turns one validated (or fallback) scene into a silent `.mp4` clip at an
exact block duration — the same "one local file per block" shape
`engine/visuals.py` already produces for AI images and stock footage, so
`engine/video.py`'s existing per-block clip assembly needs no changes at all:
a motion-graphics clip is just another `.mp4` in `image_paths[i]`.

No external API calls: frames are drawn locally with Pillow and encoded with
the ffmpeg binary the project already requires for the final render pass —
strictly cheaper and faster than an AI image per block.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import display_text, layout, schema
from .scenes import RENDERERS
from .theme import Theme, resolve_theme

DEFAULT_FPS = 25

# Phase 2.7 debug layout mode (section 10): draws the content/caption/
# platform safe-zone guides directly on every rendered frame — LOCAL only,
# disabled by default, never gated by anything but this env var so it can
# never leak into a production render by accident.
_DEBUG_LAYOUT_ENV = "MOTION_GRAPHICS_DEBUG_LAYOUT"


def debug_layout_enabled() -> bool:
    return os.environ.get(_DEBUG_LAYOUT_ENV, "").strip().lower() in ("1", "true", "yes")

# Mirrors engine/video.py's `_CRF`/preset choice for visual consistency
# across every clip in the final assembly.
_CRF = "19"


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "'ffmpeg' introuvable — installe ffmpeg (apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        tail = "\n".join((exc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"échec du rendu motion graphics (ffmpeg code {exc.returncode}) :\n{tail}") from exc


def resolve_scene(raw: object, fallback_text: str) -> dict:
    """Validated scene data, or a safe `icon_text` fallback built from the
    block's own narration/visual text — never `None`, so callers never have
    to special-case "nothing to render" (see schema.py's contract).

    Phase 2.8: the result is a `display_text.viewer_scene` — viewer fields
    only. An `icon_text` whose line was nothing but a production direction
    ("Animation: icons pop...") is empty after cleaning and gets the
    fallback line instead."""
    validated = schema.validate_scene(raw)
    if validated is not None:
        # Untouched when there is nothing to clean (the renderers apply the
        # viewer whitelist + budgets themselves, scenes._viewer_only).
        if not display_text.leaks_in_scene(validated) and not (
            validated.get("sceneType") == "icon_text" and not display_text.display_text_of(validated)
        ):
            return validated
        scene = display_text.viewer_scene(validated)
        if scene.get("sceneType") == "icon_text" and not str(scene.get("text") or "").strip():
            scene["text"] = display_text.fit_budget(display_text.strip_directions(fallback_text), "display_text") or " "
        return scene
    text = display_text.fit_budget(display_text.strip_directions(fallback_text), "display_text")
    return {"sceneType": schema.FALLBACK_SCENE_TYPE, "text": text[:140] or " "}


def render_scene_clip(
    scene: dict,
    duration: float,
    out_path: str,
    resolution: str = "1080x1920",
    fps: int = DEFAULT_FPS,
    theme_overrides: dict | None = None,
) -> str:
    """Renders `scene` (already resolved via `resolve_scene`) to `out_path`.
    Raises on an ffmpeg failure — callers (engine/visuals.py) already treat a
    single failed block visual as non-fatal, same as an OpenAI/Pexels miss."""
    width, height = (int(v) for v in resolution.split("x"))
    theme: Theme = resolve_theme(theme_overrides)
    scene_type = schema.normalized_scene_type(scene) or schema.FALLBACK_SCENE_TYPE
    render = RENDERERS.get(scene_type, RENDERERS[schema.FALLBACK_SCENE_TYPE])

    n_frames = max(1, round(max(duration, 0.1) * fps))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = out.parent / f".{out.stem}-frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    debug = debug_layout_enabled()
    try:
        for i in range(n_frames):
            t = i / max(n_frames - 1, 1)
            frame = render(scene, t, theme, (width, height))
            if debug:
                frame = layout.draw_debug_overlay(frame)
            frame.save(frames_dir / f"frame-{i:04d}.png")

        tmp_out = out.with_suffix(".tmp.mp4")
        _run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame-%04d.png"),
                "-frames:v", str(n_frames),
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", _CRF,
                str(tmp_out),
            ]
        )
        tmp_out.replace(out)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)
    return out_path
