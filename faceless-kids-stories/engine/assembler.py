"""Montage final : clips vidéo + voix off + sous-titres incrustés (via ffmpeg)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


class AssemblyError(RuntimeError):
    pass


def _run(cmd: List[str]) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AssemblyError(
            "ffmpeg/ffprobe introuvable — installe ffmpeg (apt install ffmpeg / brew install ffmpeg)"
        ) from exc
    if result.returncode != 0:
        raise AssemblyError(f"Commande ffmpeg échouée : {' '.join(cmd)}\n{result.stderr[-2000:]}")


def get_audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrapper=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AssemblyError(
            "ffprobe introuvable — installe ffmpeg (apt install ffmpeg / brew install ffmpeg)"
        ) from exc
    if result.returncode != 0:
        raise AssemblyError(f"Impossible de lire la durée de {audio_path} : {result.stderr}")
    return float(result.stdout.strip())


def build_block_clip(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Associe un clip vidéo à sa voix off, en calant la durée de la vidéo sur l'audio."""
    duration = get_audio_duration(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(video_path),
        "-i", str(audio_path),
        "-t", str(duration),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    _run(cmd)
    return output_path


def concatenate_clips(clip_paths: List[Path], output_path: Path, tmp_dir: Path) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    list_file = tmp_dir / "concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths), encoding="utf-8"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    _run(cmd)
    return output_path


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_srt = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
    style = "FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{escaped_srt}':force_style='{style}'",
        "-c:a", "copy",
        str(output_path),
    ]
    _run(cmd)
    return output_path
