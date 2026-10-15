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
RUNTIME_FILES = ("core.js", "kit-tech.js", "kit-world.js", "scene.js", "audio.js", "probe.js")
WIDTH, HEIGHT = 1080, 1920
JPEG_QUALITY = 0.95
FONT_WEIGHTS = {"Bricolage Grotesque": ("500", "600", "700", "800"), "JetBrains Mono": ("500", "700")}

_FONT_FACES = (
    ("Bricolage Grotesque", "bricolage-grotesque/BricolageGrotesque-Variable.ttf", "200 800"),
    ("JetBrains Mono", "jetbrains-mono/JetBrainsMono-Variable.ttf", "100 800"),
)


# Défense en profondeur contre le code généré : `Function.prototype.constructor` (donc `[].constructor.constructor`,
# `(()=>1).constructor`...) lève au lieu de compiler du texte. Le runtime lui-même n'utilise jamais `new Function`.
HARDEN_JS = ("Object.defineProperty(Function.prototype,'constructor',{value:function(){throw new Error('Function interdit')},"
             "writable:false,configurable:false});")


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
        + f"<script>{HARDEN_JS}</script>"
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


async def read_video_async(timeline_path) -> dict:
    """Lit `VIDEO` (duree, fps, narration, sfx) de la timeline, sans rien rendre."""
    from playwright.async_api import async_playwright

    with tempfile.TemporaryDirectory() as tmp:
        stage = build_stage_html(timeline_path, tmp)
        async with async_playwright() as p:
            browser, page = await open_page(p, stage)
            video = await page.evaluate("VIDEO")
            await browser.close()
    return video


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


def voice_inputs(voice_path) -> list[str]:
    return ["-i", str(voice_path)] if voice_path else []


def audio_args(voice_path) -> list[str]:
    """Avec une voix off : les bruitages sont baisses automatiquement quand la voix parle (sidechain), puis mixes.
    Sans voix : la piste de bruitages seule, comme en phase 1."""
    if not voice_path:
        return []
    graph = ("[2:a]asplit=2[vk][vm];[1:a]volume=0.8[sfx];"
             "[sfx][vk]sidechaincompress=threshold=0.03:ratio=10:attack=5:release=350[duck];"
             "[duck][vm]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
    return ["-filter_complex", graph, "-map", "0:v", "-map", "[mix]"]


async def render_video_async(timeline_path, out_path, voice_path=None) -> dict:
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
                 "-i", str(wav), *voice_inputs(voice_path), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                 *audio_args(voice_path), "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)],
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


async def render_segments_async(timeline_path, ranges: list[dict], out_dir) -> dict:
    """Rend seulement certains plans (`ranges` : [{id, start, duration}]) en segments MP4 sans son, plus la piste
    de bruitages entière. Sert au repli : les plans en échec sont remplacés par un clip Pillow, puis tout est recollé
    (`assemble_segments`). Renvoie {segments: {id: chemin}, sfx_wav, fps, duration, chromium}."""
    from playwright.async_api import async_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    segments: dict[str, str] = {}
    async with async_playwright() as p:
        with tempfile.TemporaryDirectory() as tmp:
            stage = build_stage_html(timeline_path, tmp)
            browser, page = await open_page(p, stage)
            duration, fps = await page.evaluate("[VIDEO.duration, VIDEO.fps]")
            sfx_wav = out_dir / "sfx.wav"
            sfx_wav.write_bytes(base64.b64decode(await page.evaluate("renderAudio()")))
            for r in ranges:
                first, last = int(round(r["start"] * fps)), int(round((r["start"] + r["duration"]) * fps))
                path = out_dir / f"segment-{r['id']}.mp4"
                ff = subprocess.Popen(
                    ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                     "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(path)],
                    stdin=subprocess.PIPE)
                for i in range(first, last):
                    ff.stdin.write(await grab(page, i / fps))
                ff.stdin.close()
                if ff.wait() != 0:
                    raise RuntimeError(f"ffmpeg a échoué sur le segment {r['id']}")
                segments[r["id"]] = str(path)
            chromium = browser.version
            await browser.close()
    return {"segments": segments, "sfx_wav": str(sfx_wav), "fps": fps, "duration": duration, "chromium": chromium}


def assemble_segments(ordered_paths: list[str], sfx_wav: str, out_path, voice_path=None, work_dir=None) -> str:
    """Recolle des segments vidéo (rendus Chromium et clips de repli normalisés), ajoute les bruitages et la voix."""
    work = Path(work_dir or Path(out_path).parent)
    listing = work / "segments.txt"
    listing.write_text("\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in ordered_paths), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(sfx_wav), *voice_inputs(voice_path),
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", *audio_args(voice_path)]
    if not voice_path:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True)
    return str(out_path)


def frame_hash(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()[:16]


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[2] == "--stills":
        paths = asyncio.run(render_stills_async(argv[0], [float(s) for s in argv[3].split(",")], argv[1]))
        print("\n".join(str(p) for p in paths))
        return 0
    if len(argv) not in (2, 4):
        print(__doc__)
        return 2
    voice = argv[argv.index("--voice") + 1] if "--voice" in argv else None
    print(json.dumps(asyncio.run(render_video_async(argv[0], argv[1], voice)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
