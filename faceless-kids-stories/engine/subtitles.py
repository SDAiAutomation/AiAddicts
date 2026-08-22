"""Génération des sous-titres (SRT) synchronisés avec la durée de chaque bloc."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple


def _format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(blocks_with_durations: Iterable[Tuple[str, float]]) -> str:
    """Construit le contenu d'un fichier SRT à partir de couples (texte, durée en secondes)."""
    lines: List[str] = []
    cursor = 0.0
    for i, (text, duration) in enumerate(blocks_with_durations, start=1):
        start = cursor
        end = cursor + duration
        lines.append(str(i))
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(text.strip())
        lines.append("")
        cursor = end
    return "\n".join(lines)


def write_srt(blocks_with_durations: Iterable[Tuple[str, float]], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_srt(blocks_with_durations), encoding="utf-8")
    return output_path
