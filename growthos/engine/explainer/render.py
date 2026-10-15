"""Rendu déterministe de l'Explainer : Chromium headless (Playwright) appelle `renderAt(t)` image par image,
ffmpeg encode.

Le code JS (runtime figé + timeline) ne tourne QUE dans Chromium, réseau coupé : toute requête hors `file:`/`data:`
est refusée. Aucune clé d'API n'entre jamais dans la page.

    python -m engine.explainer.render timeline.js out.mp4
    python -m engine.explainer.render timeline.js outdir --stills 1.2,8,20
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import RUNTIME_VERSION

HERE = Path(__file__).resolve().parent
RUNTIME_DIR = HERE / "runtime"
FONTS_DIR = HERE.parents[1] / "assets" / "fonts"
# Ordre de chargement : les scripts classiques partagent la portée globale (core avant les kits).
RUNTIME_FILES = ("core.js", "kit-tech.js", "kit-world.js", "audio.js", "probe.js")
WIDTH, HEIGHT = 1080, 1920
JPEG_QUALITY = 0.95
FONT_WEIGHTS = {"Bricolage Grotesque": ("500", "600", "700", "800"), "JetBrains Mono": ("500", "700")}

_FONT_FACES = (
    ("Bricolage Grotesque", "bricolage-grotesque/BricolageGrotesque-Variable.ttf", "200 800"),
    ("JetBrains Mono", "jetbrains-mono/JetBrainsMono-Variable.ttf", "100 800"),
)


def font_css() -> str:
    return "\n".join(
        f'@font-face{{font-family:"{name}";src:url("{(FONTS_DIR / rel).as_uri()}");font-weight:{weight}}}'
        for name, rel, weight in _FONT_FACES
    )


def build_stage_html(timeline_path: str | Path, out_dir: str | Path) -> Path:
    """Écrit la page hôte (canvas seul + runtime + timeline) dans `out_dir` et la renvoie."""
    scripts = [(RUNTIME_DIR / name).resolve().as_uri() for name in RUNTIME_FILES] + [Path(timeline_path).resolve().as_uri()]
    html = (
        '<!doctype html><meta charset="utf-8"><style>'
        f"{font_css()}html,body{{margin:0;background:#000}}canvas{{display:block}}</style>"
        f'<canvas id="c" width="{WIDTH}" height="{HEIGHT}"></canvas>'
        + "".join(f'<script src="{src}"></script>' for src in scripts)
    )
    path = Path(out_dir) / "stage.html"
    path.write_text(html, encoding="utf-8")
    return path


async def open_page(playwright, html_path: Path, inject_fonts: bool = False):
    """Ouvre `html_path` dans Chromium, réseau coupé, polices locales chargées. `inject_fonts` : pour une page tierce
    (le prototype de référence) qui référence des polices Google bloquées."""
    browser = await playwright.chromium.launch(executable_path=os.environ.get("EXPLAINER_CHROMIUM") or None)
    page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
    # Réseau coupé : seules les ressources locales passent.
    await page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "data:", "blob:")) else r.abort())
    await page.goto(html_path.resolve().as_uri())
    if inject_fonts:
        await page.add_style_tag(content=font_css())
    await page.evaluate(
        "(spec)=>Promise.all(Object.entries(spec).flatMap(([f,ws])=>ws.map(w=>document.fonts.load(w+' 80px \"'+f+'\"'))))",
        {name: list(ws) for name, ws in FONT_WEIGHTS.items()},
    )
    return browser, page


_GRAB = "(a)=>{renderFrame(a.t);return document.getElementById('c').toDataURL('image/'+a.fmt,a.q)}"


async def grab(page, t: float, fmt: str = "jpeg") -> bytes:
    data = await page.evaluate(_GRAB, {"t": t, "fmt": fmt, "q": JPEG_QUALITY})
    return base64.b64decode(data.split(",", 1)[1])


async def render_stills_async(timeline_path, times, out_dir, fmt: str = "png") -> list[Path]:
    from playwright.async_api import async_playwright

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = build_stage_html(timeline_path, tmp)
        async with async_playwright() as p:
            browser, page = await open_page(p, stage)
            paths = []
            for t in times:
                path = out / f"f{float(t):06.2f}.{'jpg' if fmt == 'jpeg' else fmt}"
                path.write_bytes(await grab(page, float(t), fmt))
                paths.append(path)
            await browser.close()
    return paths


async def render_video_async(timeline_path, out_path) -> dict:
    """Rend le MP4 complet (H.264 CRF 18, yuv420p, +faststart) avec la piste sonore synthétisée. Renvoie un rapport."""
    from playwright.async_api import async_playwright

    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        stage = build_stage_html(timeline_path, tmp)
        async with async_playwright() as p:
            browser, page = await open_page(p, stage)
            duration, fps = await page.evaluate("[VIDEO.duration, VIDEO.fps]")
            wav = Path(tmp) / "sfx.wav"
            wav.write_bytes(base64.b64decode(await page.evaluate("renderAudio()")))
            ff = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                 "-i", str(wav), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)],
                stdin=subprocess.PIPE,
            )
            frames = int(round(duration * fps))
            for i in range(frames):
                ff.stdin.write(await grab(page, i / fps))
            ff.stdin.close()
            if ff.wait() != 0:
                raise RuntimeError("ffmpeg a échoué pendant l'encodage de l'Explainer")
            chromium = browser.version
            await browser.close()
    return {
        "runtimeVersion": RUNTIME_VERSION,
        "chromium": chromium,
        "frames": frames,
        "fps": fps,
        "durationSeconds": duration,
        "renderSeconds": round(time.monotonic() - started, 1),
    }


def frame_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[2] == "--stills":
        paths = asyncio.run(render_stills_async(argv[0], [float(s) for s in argv[3].split(",")], argv[1]))
        print("\n".join(str(p) for p in paths))
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    print(json.dumps(asyncio.run(render_video_async(argv[0], argv[1])), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
