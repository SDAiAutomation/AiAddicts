"""Versions immuables d'une vidéo (lot L2, audit bible 2026-10-03).

Chaque rendu réussi (génération, rognage) devient une ligne `content_versions`
dont le fichier vit sous un chemin immuable `<id>/v<n>.mp4`. `content_items`
pointe vers la version courante ; revenir en arrière = re-pointer (fonction SQL
`restore_content_version`), sans rien régénérer ni payer.

Jamais bloquant pour la livraison : un échec d'enregistrement de la version ne
doit pas faire échouer une vidéo déjà rendue et uploadée.
"""
from pathlib import Path

from . import storage


def next_version_number(client, content_item_id: str) -> int:
    """Prochain numéro libre (1 pour le premier rendu). Un seul worker traite
    un item à la fois ; la contrainte unique (item, numéro) protège le reste."""
    rows = (
        client.table("content_versions")
        .select("version_number")
        .eq("content_item_id", content_item_id)
        .order("version_number", desc=True)
        .limit(1)
        .execute()
    )
    return (rows.data[0]["version_number"] + 1) if rows.data else 1


def upload_captions_safe(client, content_item_id: str, version: int, srt_path: Path | str | None) -> str | None:
    """Les sous-titres sont un plus : jamais d'échec de run pour eux."""
    if not srt_path or not Path(srt_path).is_file() or Path(srt_path).stat().st_size == 0:
        return None
    try:
        return storage.upload_captions(client, content_item_id, version, str(srt_path))
    except Exception as exc:
        print(f"       sous-titres .srt non archivés ({exc})")
        return None


def record_version(
    client, content_item_id: str, version: int, kind: str, video_url: str,
    poster_url: str | None = None, captions_url: str | None = None,
    script: dict | None = None, duration_seconds: float | None = None,
) -> str | None:
    """Insère la version et retourne son id, ou None si l'enregistrement
    échoue (la vidéo reste livrée, sans entrée d'historique)."""
    try:
        row = (
            client.table("content_versions")
            .insert({
                "content_item_id": content_item_id,
                "version_number": version,
                "kind": kind,
                "video_url": video_url,
                "poster_url": poster_url,
                "captions_url": captions_url,
                "script": script,
                "duration_seconds": duration_seconds,
            })
            .execute()
        )
        return row.data[0]["id"] if row.data else None
    except Exception as exc:
        print(f"       version non enregistrée ({exc})")
        return None
