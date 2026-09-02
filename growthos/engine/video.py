"""Render the final text-card video: plain background + burned captions + voiceover.

MVP deliberately skips AI-generated visuals (fal.ai / Wan 2.2 etc.): a solid
background with burned captions is enough to validate the growth loop on a
real account at near-zero cost, per the "resultats d'abord" dogfooding plan.
"""
import subprocess
from pathlib import Path

RESOLUTIONS = {
    "9:16": "1080x1920",
    "1:1": "1080x1080",
    "16:9": "1920x1080",
}

DEFAULT_BG = "0x0F172A"  # matches the GrowthOS design system's dark surface


def concat_audio(audio_paths: list[str], out_path: str) -> str:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    list_file = str(Path(out_path).with_suffix(".txt"))
    Path(list_file).write_text(
        "\n".join(f"file '{Path(p).resolve()}'" for p in audio_paths), encoding="utf-8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", out_path],
        check=True, capture_output=True,
    )
    return out_path


def render_final(
    audio_path: str,
    srt_path: str,
    out_path: str,
    aspect_ratio: str = "9:16",
    bg_color: str = DEFAULT_BG,
) -> str:
    resolution = RESOLUTIONS.get(aspect_ratio, RESOLUTIONS["9:16"])
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # burn subtitles: white text, semi-bold, centered lower third
    style = (
        "FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Alignment=2,MarginV=140"
    )
    subtitles_filter = f"subtitles={Path(srt_path).as_posix()}:force_style='{style}'"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={bg_color}:s={resolution}",
            "-i", audio_path,
            "-vf", subtitles_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return out_path
