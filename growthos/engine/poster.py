"""Poster (image fixe) d'une vidéo rendue.

Les listes (/content, dashboard) affichaient une balise <video> par ligne juste
pour montrer un premier frame : chaque affichage pouvait re-télécharger des
dizaines de Mo par vidéo et a fait dépasser le quota d'egress Supabase. Un
JPEG de quelques dizaines de Ko le remplace.
"""
from pathlib import Path

from .video import _run

# 270x480 = 9:16 ; largement net pour une miniature de liste, y compris écran
# haute densité, et reste à ~15-25 Ko.
POSTER_WIDTH = 270
# Un peu après le début : le tout premier frame est souvent noir (fondu).
POSTER_AT_S = 0.3


def build_poster_args(src: str, out: str, at_s: float = POSTER_AT_S) -> list[str]:
    return [
        "ffmpeg", "-y", "-ss", f"{at_s:.3f}", "-i", src,
        "-frames:v", "1", "-vf", f"scale={POSTER_WIDTH}:-2",
        "-q:v", "4", out,
    ]


def extract_poster(src: str, out_path: str, at_s: float = POSTER_AT_S) -> str:
    """Écrit un JPEG du frame à `at_s` secondes de `src` (fichier local ou URL
    http). Lève si ffmpeg échoue ou ne produit rien — à l'appelant de traiter
    le poster comme facultatif (la vidéo reste valable sans)."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    _run(build_poster_args(src, out_path, at_s))
    if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
        raise RuntimeError("ffmpeg n'a produit aucun poster")
    return out_path
