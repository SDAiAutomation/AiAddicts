"""Render the final text-card video: plain background + burned captions + voiceover.

MVP deliberately skips AI-generated visuals (fal.ai / Wan 2.2 etc.): a solid
background with burned captions is enough to validate the growth loop on a
real account at near-zero cost, per the "resultats d'abord" dogfooding plan.
"""
import os
import subprocess
from pathlib import Path

RESOLUTIONS = {
    "9:16": "1080x1920",
    "1:1": "1080x1080",
    "16:9": "1920x1080",
}

DEFAULT_BG = "0x0F172A"  # matches the GrowthOS design system's dark surface

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


def render_final(
    audio_path: str,
    srt_path: str,
    out_path: str,
    aspect_ratio: str = "9:16",
    bg_color: str = DEFAULT_BG,
    font: str | None = None,
) -> str:
    resolution = RESOLUTIONS.get(aspect_ratio, RESOLUTIONS["9:16"])
    font = font or os.environ.get("SUBTITLE_FONT") or DEFAULT_FONT

    srt = Path(srt_path)
    audio_abs = Path(audio_path).resolve()
    out_abs = Path(out_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    # burn subtitles: white text, semi-bold, centered lower third
    style = (
        f"FontName={font},FontSize=16,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Alignment=2,MarginV=140"
    )
    # Reference the .srt by bare name with cwd set to its folder: the ffmpeg
    # `subtitles` filter mis-parses Windows drive letters (C:\) and backslashes
    # when they appear in the filename argument.
    subtitles_filter = f"subtitles={srt.name}:force_style='{style}'"

    _run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={resolution}",
            "-i", str(audio_abs),
            "-vf", subtitles_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(out_abs),
        ],
        cwd=str(srt.parent),
    )
    return out_path
