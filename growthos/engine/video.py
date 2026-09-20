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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RESOLUTIONS = {
    "9:16": "1080x1920",
    "1:1": "1080x1080",
    "16:9": "1920x1080",
}

# Chaque clip par bloc est un rendu ffmpeg indépendant (CPU-bound, mais
# subprocess.run libère le GIL pendant que ffmpeg tourne) : plusieurs en
# parallèle raccourcissent le "somme des clips" à ~"clip le plus long",
# plafonné aux cœurs dispo pour ne pas suroccuper la machine (même logique
# que _MAX_TTS_WORKERS / _MAX_IMAGE_WORKERS, adaptée au CPU plutôt qu'au réseau).
_MAX_CLIP_WORKERS = max(1, min(4, os.cpu_count() or 4))

DEFAULT_BG = "0x0F172A"  # matches the GrowthOS design system's dark surface
DEFAULT_FPS = 25
MAX_SHOT_DURATION_S = 3.0

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


def prepend_silence(audio_path: str, seconds: float, out_path: str) -> str:
    """Prefix an audio track with exact silence, used by the quiz cover scene."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-f", "lavfi", "-t", f"{seconds:.3f}",
        "-i", "anullsrc=r=44100:cl=stereo", "-i", str(Path(audio_path).resolve()),
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]", "-map", "[out]", str(out.resolve()),
    ])
    return out_path


def pad_audio(audio_path: str, extra_seconds: float, out_path: str) -> str:
    """Ajoute un silence à la fin d'un bloc, notamment pour le compte à rebours."""
    if extra_seconds <= 0:
        return audio_path
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(Path(audio_path).resolve()),
        "-af", f"apad=pad_dur={extra_seconds:.3f}", "-c:a", "libmp3lame", "-q:a", "2",
        str(out.resolve()),
    ])
    return out_path


_QUIZ_BEEP_FREQUENCIES = {
    "studio": 880, "arcade": 1040, "education": 740, "sport": 920,
    "pop": 980, "minimal": 660, "photo": 880, "logo": 820,
}


def add_countdown_sfx(
    audio_path: str,
    narration_seconds: float,
    countdown_seconds: int,
    out_path: str,
    mode: str = "automatic",
    theme: str = "studio",
) -> str:
    """Pad a narration block and mix one short beep at each countdown tick."""
    if countdown_seconds <= 0 or mode == "off":
        return pad_audio(audio_path, countdown_seconds, out_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frequency = _QUIZ_BEEP_FREQUENCIES.get(theme, 880)
    volume = 0.08 if mode == "subtle" else 0.16
    inputs = ["-i", str(Path(audio_path).resolve())]
    filters = [f"[0:a]apad=pad_dur={countdown_seconds:.3f}[base]"]
    labels = ["[base]"]
    for index in range(countdown_seconds):
        tick_frequency = frequency + (180 if index == countdown_seconds - 1 else 0)
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={tick_frequency}:duration=0.10"]
        delay_ms = round((narration_seconds + index) * 1000)
        label = f"b{index}"
        filters.append(f"[{index + 1}:a]volume={volume},adelay={delay_ms}|{delay_ms}[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0[out]")
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(out.resolve())])
    return out_path


def _exists_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


_VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

# Ken Burns : un mouvement différent par bloc (choisi par l'index du bloc,
# stable au re-rendu) pour éviter l'effet "toutes les images zooment pareil".
_KB_MOVES = ("in", "out", "right", "left", "up", "in_slow")

# Vignette légère qui "respire" (angle animé) : un cadrage un peu filmique,
# coût de compression négligeable. Appliquée aux clips image ET stock.
_VIGNETTE = "vignette=angle='PI/4.5+0.05*sin(2*PI*t/7)':eval=frame"

# CRF x264 (défaut ffmpeg 23) : 19 est nettement plus net à l'œil sans faire
# exploser la taille de fichier, à "veryfast" constant (on ne touche pas au
# preset, ça grossirait trop le temps de rendu). Appliqué à tous les encodages
# libx264 du pipeline (clips par bloc + assemblage final).
_CRF = "19"

# Ken Burns : zoompan lit une image déjà à la résolution de sortie (ex.
# 1080x1920) et zoome dedans -> la zone zoomée est ré-agrandie depuis moins de
# pixels que la sortie, ce qui pixellise visiblement en fin de zoom. On
# sur-échantillonne la source AVANT zoompan (elle rescale ensuite vers
# `resolution` via son propre `s=`) : plus de pixels à interpoler pendant le
# zoom, mouvement plus net. Coût : rendu plus long (plus de pixels à traiter).
_KENBURNS_SUPERSAMPLE = 2


def _scaled_resolution(resolution: str, factor: int) -> str:
    w, h = resolution.split("x")
    return f"{int(w) * factor}x{int(h) * factor}"


def _kenburns_filter(move: str, resolution: str, n_frames: int, fps: int) -> str:
    """Expression `zoompan` pour un mouvement Ken Burns donné. L'image est déjà
    scalée+croppée à `resolution` en amont, donc iw/ih = W/H cible."""
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    n = max(n_frames, 1)
    if move == "out":
        z, x, y = f"if(eq(on,0),1.28,max(1.28-0.0016*on,1.03))", cx, cy
    elif move == "right":
        z, x, y = "1.14", f"(iw-iw/zoom)*on/{n}", cy
    elif move == "left":
        z, x, y = "1.14", f"(iw-iw/zoom)*(1-on/{n})", cy
    elif move == "up":
        z, x, y = "1.14", cx, f"(ih-ih/zoom)*(1-on/{n})"
    elif move == "in_slow":
        z, x, y = "min(1.0+0.0009*on,1.15)", cx, cy
    else:  # "in"
        z, x, y = "min(1.0+0.0016*on,1.28)", cx, cy
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={n_frames}:s={resolution}:fps={fps}"


def _render_block_clip(
    image_path: str | None,
    duration: float,
    out_path: str,
    resolution: str,
    bg_color: str,
    fps: int,
    block_index: int = 1,
    source_offset: float = 0.0,
) -> str:
    """Un clip silencieux pour un bloc :
    - `.mp4/.mov/...` -> clip vidéo de stock, recadré plein cadre, bouclé/coupé
      à la durée du bloc (pas de Ken Burns, il bouge déjà) ;
    - image -> Ken Burns (mouvement variable selon `block_index`) ;
    - None -> fond couleur unie."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, round(duration * fps))

    if image_path and image_path.lower().endswith(_VIDEO_EXTS):
        vf = (
            f"scale={resolution}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={resolution.replace('x', ':')},fps={fps},{_VIGNETTE},format=yuv420p"
        )
        _run(
            [
                "ffmpeg", "-y",
                # boucle le clip source s'il est plus court que le bloc ;
                # `-t` coupe s'il est plus long. `-an` : on jette l'audio.
                "-stream_loop", "-1", "-i", str(Path(image_path).resolve()),
                "-ss", f"{source_offset:.3f}",
                "-t", f"{duration:.3f}",
                "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
                "-crf", _CRF, "-an",
                str(out.resolve()),
            ]
        )
    elif image_path:
        # Sur-cadre (sur-échantillonné, voir _KENBURNS_SUPERSAMPLE) puis crop
        # avant le zoom : sinon le zoompan révèle les bords de l'image source
        # dès qu'il recadre.
        move = _KB_MOVES[(block_index - 1) % len(_KB_MOVES)]
        super_res = _scaled_resolution(resolution, _KENBURNS_SUPERSAMPLE)
        vf = (
            f"scale={super_res}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={super_res.replace('x', ':')},"
            f"{_kenburns_filter(move, resolution, n_frames, fps)},"
            f"{_VIGNETTE},format=yuv420p"
        )
        _run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(Path(image_path).resolve()),
                "-t", f"{duration:.3f}",
                "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
                "-crf", _CRF, "-an",
                str(out.resolve()),
            ]
        )
    else:
        _run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c={bg_color}:s={resolution}:r={fps}",
                "-t", f"{duration:.3f}", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                "-crf", _CRF,
                # Fond fixe, aucun mouvement réel : tuning x264 dédié.
                "-tune", "stillimage", "-an",
                str(out.resolve()),
            ]
        )
    return out_path


def plan_shots(
    durations: list[float],
    image_paths: list[str | None] | None = None,
    max_duration: float = MAX_SHOT_DURATION_S,
) -> list[tuple[int, str | None, float, float]]:
    """Découpe chaque bloc en plans courts sans changer sa durée totale.

    Retourne `(index du bloc, visuel, durée, offset dans le bloc)` par plan.
    """
    if max_duration <= 0:
        raise ValueError("max_duration doit être strictement positif")
    visuals = list(image_paths or [])
    visuals.extend([None] * (len(durations) - len(visuals)))
    shots: list[tuple[int, str | None, float, float]] = []
    for block_index, duration in enumerate(durations, start=1):
        visual = visuals[block_index - 1]
        remaining = max(float(duration), 0.0)
        offset = 0.0
        while remaining > 1e-6:
            shot_duration = min(max_duration, remaining)
            shots.append((block_index, visual, shot_duration, offset))
            offset += shot_duration
            remaining -= shot_duration
    return shots


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

    shots = plan_shots(durations, image_paths)
    n_clips = len(shots)
    clip_names = []
    pending: list[tuple[int, int, str | None, float, float, Path]] = []
    for i, (block_index, image_path, duration, source_offset) in enumerate(shots, start=1):
        clip_path = clips_dir / f"shot-{i:03d}.mp4"
        clip_names.append(clip_path.name)
        if _exists_nonempty(clip_path):
            print(f"       plan {i}/{n_clips} déjà rendu — réutilisé")
        else:
            pending.append((i, block_index, image_path, duration, source_offset, clip_path))

    if pending:
        def _render(item: tuple[int, int, str | None, float, float, Path]) -> None:
            i, block_index, image_path, duration, source_offset, clip_path = item
            print(f"       plan {i}/{n_clips} — bloc {block_index} ({duration:.1f}s)…")
            t0 = time.monotonic()
            _render_block_clip(
                image_path, duration, str(clip_path), resolution, bg_color, fps,
                block_index=i, source_offset=source_offset,
            )
            print(f"       plan {i}/{n_clips} terminé en {time.monotonic() - t0:.1f}s")

        with ThreadPoolExecutor(max_workers=min(_MAX_CLIP_WORKERS, len(pending))) as pool:
            list(pool.map(_render, pending))

    # Le demuxer concat résout les chemins de la liste relativement au
    # dossier de la liste elle-même (vérifié) — noms de fichiers bruts, tous
    # dans clips_dir, aucune ambiguïté.
    list_path = clips_dir / "list.txt"
    list_path.write_text("\n".join(f"file '{name}'" for name in clip_names), encoding="utf-8")

    # Reference the caption file (et la liste concat) par chemin relatif avec
    # cwd sur work_dir : le filtre `subtitles` d'ffmpeg mal-parse les lettres
    # de lecteur Windows (C:\) et les antislashs dans un argument de filtre.
    if srt.suffix == ".ass":
        # Le style (police, contour, boîte, surlignage) est embarqué dans le
        # .ass — voir engine/captions.write_ass / `caption_style` du script.
        subtitles_filter = f"subtitles={srt.name}"
    else:
        # Repli .srt : style unique historique.
        style = (
            f"FontName={font},FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
            "Alignment=2,MarginV=140"
        )
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
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", _CRF,
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            # Index de lecture (moov) en tête de fichier : le navigateur peut
            # lire/afficher sans télécharger la fin du MP4 d'abord.
            "-movflags", "+faststart",
            str(out_abs),
        ],
        cwd=str(srt.parent),
    )
    print(f"       assemblage final terminé en {time.monotonic() - t0:.1f}s")
    return out_path
