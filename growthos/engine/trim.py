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
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

from . import poster, storage, versions
from .video import _CRF, _run  # même remontée d'erreur ffmpeg lisible

# Clip minimal : en dessous, `trim_end - trim_start` ne fait plus une vidéo.
_MIN_CLIP_S = 0.5

# Source du rognage : bornée en taille et en temps TOTAL (le délai de lecture de requests ne borne que
# l'attente entre deux octets, pas la durée du téléchargement) et validée comme un vrai MP4 avant tout
# traitement ou republication.
MAX_DOWNLOAD_BYTES = int(os.environ.get("TRIM_MAX_DOWNLOAD_BYTES", 300 * 1024 * 1024))
MAX_DOWNLOAD_SECONDS = int(os.environ.get("TRIM_MAX_DOWNLOAD_SECONDS", 300))
MAX_DURATION_S = int(os.environ.get("TRIM_MAX_DURATION_SECONDS", 900))
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_QUERY_RE = re.compile(r"^(?:[vt]=\d{1,12})?$")  # `?v=` (rendu) et `?t=` (_bust) : cache-busters uniquement
# Messages génériques : fail_trim() enregistre str(exc) dans trim_error, que l'utilisateur peut lire.
_REFUSED = "Source vidéo non autorisée."
_INVALID = "Source vidéo invalide."


def is_trusted_storage_url(url, content_item_id, supabase_url) -> bool:
    """Vrai seulement pour une vidéo de CE contenu dans le bucket public du projet : même schéma, même
    hôte et même port que SUPABASE_URL, chemin `/storage/v1/object/public/content-videos/<id>` suivi de
    `.mp4`, `.original.mp4` ou `/v<n>.mp4`, sans identifiants, fragment ni requête autre qu'un
    cache-buster. Les écritures de ces URL par les clients sont fermées côté base ; ce contrôle protège
    le worker même si une URL arbitraire parvenait malgré tout dans la ligne."""
    if not isinstance(url, str) or not isinstance(supabase_url, str) or not url or url != url.strip():
        return False
    if not _UUID_RE.match(str(content_item_id)):
        return False
    if "#" in url or any(ch in url for ch in ("\\", "\n", "\r", "\t", " ")):
        return False
    try:
        parsed, base = urlsplit(url), urlsplit(supabase_url)
    except ValueError:
        return False
    scheme = parsed.scheme.lower()
    if scheme not in ("https", "http") or scheme != base.scheme.lower():
        return False
    if "@" in parsed.netloc or parsed.netloc.lower() != base.netloc.lower():
        return False
    if not _QUERY_RE.match(parsed.query):
        return False
    path = rf"/storage/v1/object/public/content-videos/{re.escape(str(content_item_id))}(?:\.mp4|\.original\.mp4|/v[1-9]\d{{0,5}}\.mp4)"
    return re.fullmatch(path, parsed.path) is not None


def validate_video_file(path) -> None:
    """Refuse tout ce qui n'est pas un MP4/MOV avec une piste vidéo et une durée plausible. ffprobe ne peut
    ouvrir que des fichiers locaux (`-protocol_whitelist file`) : une playlist HLS ou un fichier
    « concat » qui pointerait vers une adresse distante est rejeté sans qu'aucune requête réseau soit faite."""
    cmd = ["ffprobe", "-v", "error", "-protocol_whitelist", "file",
           "-show_entries", "format=format_name,duration:stream=codec_type", "-of", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(_INVALID) from None
    if proc.returncode != 0:
        raise ValueError(_INVALID)
    try:
        info = json.loads(proc.stdout)
        fmt = info.get("format") or {}
        formats = set(str(fmt.get("format_name") or "").split(","))
        duration = float(fmt.get("duration"))
        has_video = any(s.get("codec_type") == "video" for s in info.get("streams") or [])
    except (ValueError, TypeError, AttributeError):
        raise ValueError(_INVALID) from None
    if not (formats & {"mp4", "mov"}) or not has_video or not (0.5 <= duration <= MAX_DURATION_S):
        raise ValueError(_INVALID)


def build_trim_args(src: str, out: str, start: float, end: float | None) -> list[str]:
    """Commande ffmpeg de découpe. `-ss` avant `-i` (seek rapide au keyframe
    le plus proche, précision largement suffisante pour couper l'amorce ou la
    chute d'une vidéo parlée) ; `-t` borne la durée quand une fin est fixée.
    Réencode (les points de coupe ne tombent pas sur des keyframes) avec les
    mêmes réglages que le rendu final (engine/video.render_final)."""
    args = ["ffmpeg", "-y"]
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    # Entrée limitée aux fichiers locaux : aucun protocole réseau ne peut être ouvert par le décodeur.
    args += ["-protocol_whitelist", "file", "-i", src]
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


def _download(url: str, dest: Path, *, content_item_id: str, supabase_url: str | None = None) -> None:
    """Télécharge la source d'un contenu depuis le stockage du projet, rien d'autre : URL contrôlée AVANT
    toute requête, redirections refusées, taille et durée totales bornées, fichier partiel supprimé."""
    supabase_url = supabase_url or os.environ.get("SUPABASE_URL", "")
    if not is_trusted_storage_url(url, content_item_id, supabase_url):
        raise ValueError(_REFUSED)
    dest.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=False) as resp:
            if 300 <= resp.status_code < 400:
                raise ValueError(_REFUSED)
            resp.raise_for_status()
            declared = resp.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Source vidéo trop volumineuse.")
            total = 0
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise ValueError("Source vidéo trop volumineuse.")
                    if time.monotonic() - started > MAX_DOWNLOAD_SECONDS:
                        raise ValueError("Téléchargement de la source trop long.")
                    fh.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def _poster_fields(client, content_item_id: str, video_path: Path) -> dict:
    """Le premier frame change avec le rognage : on régénère la miniature.
    Facultatif — un échec laisse l'ancien poster en place plutôt que de faire
    échouer un rognage par ailleurs réussi."""
    try:
        poster_path = poster.extract_poster(str(video_path), str(video_path.parent / "poster.jpg"))
        return {"poster_url": storage.upload_poster(client, content_item_id, poster_path)}
    except Exception as exc:
        print(f"       poster non régénéré ({exc})")
        return {}


def apply_trim(client, item: dict, output_root: str = "output") -> dict:
    """`item` = ligne réclamée par repo.claim_trim_job :
    {id, video_url, original_video_url, trim_start, trim_end}.

    Retourne les champs à réécrire sur le content_item :
    {video_url, original_video_url, trim_start, trim_end} (+ poster_url si la
    miniature a pu être régénérée).
    """
    content_item_id = item["id"]
    start = float(item.get("trim_start") or 0.0)
    raw_end = item.get("trim_end")
    end = float(raw_end) if raw_end is not None else None

    have_original = bool(item.get("original_video_url"))
    source_url = item["original_video_url"] if have_original else item["video_url"]

    work = Path(output_root) / "trim" / content_item_id
    src = work / "source.mp4"
    _download(source_url, src, content_item_id=content_item_id)
    validate_video_file(src)  # vrai MP4 local avant toute découpe, archivage ou republication

    # Chaque résultat devient une version immuable (lot L2) : le fichier n'est
    # plus écrasé, « rétablir » et « rogner » ajoutent à l'historique.
    try:
        version_number = versions.next_version_number(client, content_item_id)
    except Exception as exc:
        print(f"       (historique de versions indisponible : {exc})")
        version_number = None

    def _with_version(fields: dict, url: str, poster_url: str | None) -> dict:
        if version_number:
            version_id = versions.record_version(
                client, content_item_id, version_number, "trim", url,
                poster_url=poster_url,
            )
            if version_id:
                fields["current_version_id"] = version_id
        return fields

    # start <= 0 et pas de fin => « rétablir la version complète » : on
    # republie la source intacte telle quelle et on oublie l'archive.
    if start <= 0 and end is None:
        if have_original and storage.is_versioned_url(source_url):
            restored_url = source_url  # déjà immuable : rien à renvoyer
        else:
            restored_url = storage.upload_video(client, content_item_id, str(src), version=version_number)
        poster_fields = _poster_fields(client, content_item_id, src)
        return _with_version({
            "video_url": restored_url if version_number else _bust(restored_url),
            "original_video_url": None,
            "trim_start": 0,
            "trim_end": None,
            **poster_fields,
        }, restored_url, poster_fields.get("poster_url"))

    original_url = item.get("original_video_url")
    if not have_original:
        if storage.is_versioned_url(item.get("video_url")):
            original_url = item["video_url"]  # la version d'origine est déjà conservée
        else:
            # Historique : archiver la source AVANT que upload_video l'écrase.
            original_url = storage.upload_original(client, content_item_id, str(src))

    out = work / "trimmed.mp4"
    _run(build_trim_args(str(src.resolve()), str(out.resolve()), start, end))

    trimmed_url = storage.upload_video(client, content_item_id, str(out), version=version_number)
    poster_fields = _poster_fields(client, content_item_id, out)
    return _with_version({
        "video_url": trimmed_url if version_number else _bust(trimmed_url),
        "original_video_url": original_url,
        "trim_start": start,
        "trim_end": end,
        **poster_fields,
    }, trimmed_url, poster_fields.get("poster_url"))
