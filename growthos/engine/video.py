"""Render the final video: per-block visuals + burned captions + voiceover.

Chaque bloc a son propre clip silencieux de la durée de sa voix off — une
photo Pexels avec un effet Ken Burns (zoom lent) si `visuals.fetch_block_images`
en a trouvé une, sinon un fond couleur unie (comportement d'origine du MVP,
conservé comme repli : pas de PEXELS_API_KEY -> pas de visuel -> ça marche
quand même). Les clips sont concaténés, sous-titrés et mixés avec l'audio en
une dernière passe.
"""
import os
import subprocess
import time
from pathlib import Path

RESOLUTIONS = {
    "9:16": "1080x1920",
    "1:1": "1080x1080",
    "16:9": "1920x1080",
}

DEFAULT_BG = "0x0F172A"  # matches the GrowthOS design system's dark surface
DEFAULT_FPS = 25

# libass substitue silencieusement une police par défaut si celle-ci est absente
# (cas d'un serveur/CI Linux sans Arial) ; surchargeable via SUBTITLE_FONT.
DEFAULT_FONT = "Arial"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run an ffmpeg/ffprobe command, surfacing a readable error on failure."""
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"'{cmd[0]}' introuvable — installe ffmpeg "
            "(apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        tail = "\n".join((exc.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"échec de {cmd[0]} (code {exc.returncode}) :\n{tail}") from exc


def concat_audio(audio_paths: list[str], out_path: str) -> str:
    """Concatenate the per-block audio into one gapless track.

    Uses the concat *filter* (decode then join samples) rather than the concat
    demuxer with stream copy: the latter keeps every mp3's encoder delay/padding,
    which adds up to a few hundred ms of silent gaps over a full script and
    drifts the burned captions. Output is WAV to stay lossless before the final
    AAC encode.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    for p in audio_paths:
        inputs += ["-i", str(Path(p).resolve())]
    n = len(audio_paths)
    graph = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"

    _run(["ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", str(out)])
    return out_path


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _render_block_clip(
    image_path: str | None,
    duration: float,
    out_path: str,
    resolution: str,
    bg_color: str,
    fps: int,
) -> str:
    """Un clip silencieux pour un bloc : Ken Burns sur `image_path` si fourni
    (image plein cadre, léger zoom continu), sinon fond couleur unie."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, round(duration * fps))

    if image_path:
        # Sur-cadre puis crop à la résolution cible avant le zoom : sinon le
        # zoompan révèle les bords de l'image source dès qu'il recadre.
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=increase,"
            f"crop={resolution.replace('x', ':')},"
            f"zoompan=z='min(zoom+0.0015,1.2)':d={n_frames}:s={resolution}:fps={fps},"
            "format=yuv420p"
        )
        _run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(Path(image_path).resolve()),
                "-t", f"{duration:.3f}",
                "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-an",
                str(out.resolve()),
            ]
        )
    else:
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={resolution}:r={fps}",
                "-t", f"{duration:.3f}", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                # Fond fixe, aucun mouvement réel : tuning x264 dédié.
                "-tune", "stillimage", "-an",
                str(out.resolve()),
            ]
        )
    return out_path


def render_final(
    audio_path: str,
    srt_path: str,
    out_path: str,
    durations: list[float],
    image_paths: list[str | None] | None = None,
    aspect_ratio: str = "9:16",
    bg_color: str = DEFAULT_BG,
    font: str | None = None,
    fps: int = DEFAULT_FPS,
) -> str:
    """`durations` = durée (s) de chaque bloc, dans l'ordre — sert à caler un
    clip par bloc sur sa voix off. `image_paths` (même longueur, ou None pour
    tout en fond uni) = image locale par bloc, ou None pour ce bloc précis
    (repli fond uni, jamais bloquant)."""
    resolution = RESOLUTIONS.get(aspect_ratio, RESOLUTIONS["9:16"])
    font = font or os.environ.get("SUBTITLE_FONT") or DEFAULT_FONT
    image_paths = image_paths or [None] * len(durations)

    srt = Path(srt_path)
    audio_abs = Path(audio_path).resolve()
    out_abs = Path(out_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    clips_dir = srt.parent / "clips"

    n_clips = len(durations)
    clip_names = []
    for i, (image_path, duration) in enumerate(zip(image_paths, durations), start=1):
        clip_path = clips_dir / f"block-{i:02d}.mp4"
        if _exists_nonempty(clip_path):
            print(f"       clip {i}/{n_clips} déjà rendu — réutilisé")
        else:
            print(f"       clip {i}/{n_clips} ({duration:.1f}s)…")
            t0 = time.monotonic()
            _render_block_clip(image_path, duration, str(clip_path), resolution, bg_color, fps)
            print(f"       clip {i}/{n_clips} terminé en {time.monotonic() - t0:.1f}s")
        clip_names.append(clip_path.name)

    # Le demuxer concat résout les chemins de la liste relativement au
    # dossier de la liste elle-même (vérifié) — noms de fichiers bruts, tous
    # dans clips_dir, aucune ambiguïté.
    list_path = clips_dir / "list.txt"
    list_path.write_text("\n".join(f"file '{name}'" for name in clip_names), encoding="utf-8")

    # burn subtitles: white text, semi-bold, centered lower third
    style = (
        f"FontName={font},FontSize=16,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Alignment=2,MarginV=140"
    )
    # Reference the .srt (et la liste concat) par chemin relatif avec cwd sur
    # work_dir : le filtre `subtitles` d'ffmpeg mal-parse les lettres de
    # lecteur Windows (C:\) et les antislashs dans un argument de filtre.
    subtitles_filter = f"subtitles={srt.name}:force_style='{style}'"

    print(f"       assemblage final ({n_clips} clips + sous-titres)…")
    t0 = time.monotonic()
    _run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(Path("clips") / "list.txt"),
            "-i", str(audio_abs),
            "-vf", subtitles_filter,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-shortest",
            str(out_abs),
        ],
        cwd=str(srt.parent),
    )
    print(f"       assemblage final terminé en {time.monotonic() - t0:.1f}s")
    return out_path
