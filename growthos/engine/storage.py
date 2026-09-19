"""Upload rendered videos to Supabase Storage.

Sans ça, `content_items.video_url` n'est qu'un chemin de fichier local à la
machine qui a fait tourner le pipeline — personne d'autre ne peut voir la
vidéo. Le bucket `content-videos` est public en lecture (policy côté bucket,
voir la migration `content_videos_bucket`) ; seul service_role peut y écrire
(RLS par défaut = deny, service_role la contourne — même modèle que le reste
du schéma, voir engine/db.py).
"""
import time
from pathlib import Path

BUCKET = "content-videos"

# Un an. Les chemins sont réécrits en place (upsert) à chaque régénération ou
# rognage : l'URL publique porte donc un `?v=<timestamp>` qui change avec le
# contenu, ce qui rend un cache long sûr (une nouvelle version = nouvelle URL).
_CACHE_SECONDS = "31536000"


def upload_video(client, content_item_id: str, local_path: str) -> str:
    """Upload `local_path` sous `<content_item_id>.mp4` (upsert : régénérer
    écrase la version précédente au même chemin). Retourne l'URL publique.
    Lève une exception si l'upload échoue — à l'appelant de décider s'il
    retombe sur le chemin local plutôt que de faire échouer tout le run."""
    return _upload(client, f"{content_item_id}.mp4", local_path, "video/mp4")


def upload_original(client, content_item_id: str, local_path: str) -> str:
    """Archive la version non rognée sous `<content_item_id>.original.mp4`, au
    premier rognage — `upload_video` écrase ensuite `<id>.mp4` par la version
    coupée, celle-ci reste la source intacte pour « rétablir la version
    complète » ou re-rogner plus large. Retourne son URL publique."""
    return _upload(client, f"{content_item_id}.original.mp4", local_path, "video/mp4")


def upload_poster(client, content_item_id: str, local_path: str) -> str:
    """Miniature JPEG sous `<content_item_id>.jpg` (voir engine/poster.py)."""
    return _upload(client, f"{content_item_id}.jpg", local_path, "image/jpeg")


def _upload(client, storage_path: str, local_path: str, content_type: str) -> str:
    client.storage.from_(BUCKET).upload(
        storage_path,
        str(Path(local_path).resolve()),
        file_options={
            "content-type": content_type,
            "upsert": "true",
            "cache-control": _CACHE_SECONDS,
        },
    )
    url = client.storage.from_(BUCKET).get_public_url(storage_path)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}v={int(time.time())}"
