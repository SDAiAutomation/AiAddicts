"""Rogne (coupe début et/ou fin) la vidéo finale déjà rendue d'un content_item.

Séparé du pipeline de génération (assembler.py) : on repart du MP4 déjà produit
et stocké dans Supabase Storage, sans repasser ni par ElevenLabs ni par le
rendu des clips. Piloté par la file `content_items.trim_status`
('pending' -> worker), pas par le `status` principal — la vidéo reste
consultable et publiable pendant ce temps.

Au premier rognage, la source intacte est archivée sous
`<id>.original.mp4` : elle sert au « rétablir la version complète » et à
re-rogner plus large ensuite (on repart toujours de l'original, jamais d'une
version déjà coupée).
"""
import time
from pathlib import Path

import requests

from . import storage
from .video import _CRF, _run  # même remontée d'erreur ffmpeg lisible

# Clip minimal : en dessous, `trim_end - trim_start` ne fait plus une vidéo.
_MIN_CLIP_S = 0.5


def build_trim_args(src: str, out: str, start: float, end: float | None) -> list[str]:
    """Commande ffmpeg de découpe. `-ss` avant `-i` (seek rapide au keyframe
    le plus proche, précision largement suffisante pour couper l'amorce ou la
    chute d'une vidéo parlée) ; `-t` borne la durée quand une fin est fixée.
    Réencode (les points de coupe ne tombent pas sur des keyframes) avec les
    mêmes réglages que le rendu final (engine/video.render_final)."""
    args = ["ffmpeg", "-y"]
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", src]
    if end is not None:
        args += ["-t", f"{max(_MIN_CLIP_S, end - start):.3f}"]
    args += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", _CRF,
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        out,
    ]
    return args


def _bust(url: str) -> str:
    """Cache-buster : le chemin de storage (`<id>.mp4`) ne change pas d'un
    rognage à l'autre, sans ça le CDN / le <video> du front resservent
    l'ancienne version."""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(time.time())}"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)


def apply_trim(client, item: dict, output_root: str = "output") -> dict:
    """`item` = ligne réclamée par repo.claim_trim_job :
    {id, video_url, original_video_url, trim_start, trim_end}.

    Retourne les champs à réécrire sur le content_item :
    {video_url, original_video_url, trim_start, trim_end}.
    """
    content_item_id = item["id"]
    start = float(item.get("trim_start") or 0.0)
    raw_end = item.get("trim_end")
    end = float(raw_end) if raw_end is not None else None

    have_original = bool(item.get("original_video_url"))
    source_url = item["original_video_url"] if have_original else item["video_url"]

    work = Path(output_root) / "trim" / content_item_id
    src = work / "source.mp4"
    _download(source_url, src)

    # start <= 0 et pas de fin => « rétablir la version complète » : on
    # republie la source intacte telle quelle et on oublie l'archive.
    if start <= 0 and end is None:
        restored_url = storage.upload_video(client, content_item_id, str(src))
        return {
            "video_url": _bust(restored_url),
            "original_video_url": None,
            "trim_start": 0,
            "trim_end": None,
        }

    original_url = item.get("original_video_url")
    if not have_original:
        # 1er rognage : archiver la source AVANT que upload_video l'écrase.
        original_url = storage.upload_original(client, content_item_id, str(src))

    out = work / "trimmed.mp4"
    _run(build_trim_args(str(src.resolve()), str(out.resolve()), start, end))

    trimmed_url = storage.upload_video(client, content_item_id, str(out))
    return {
        "video_url": _bust(trimmed_url),
        "original_video_url": original_url,
        "trim_start": start,
        "trim_end": end,
    }
