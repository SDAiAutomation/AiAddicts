"""Upload rendered videos to Supabase Storage.

Sans ça, `content_items.video_url` n'est qu'un chemin de fichier local à la
machine qui a fait tourner le pipeline — personne d'autre ne peut voir la
vidéo. Le bucket `content-videos` est public en lecture (policy côté bucket,
voir la migration `content_videos_bucket`) ; seul service_role peut y écrire
(RLS par défaut = deny, service_role la contourne — même modèle que le reste
du schéma, voir engine/db.py).
"""
from pathlib import Path

BUCKET = "content-videos"


def upload_video(client, content_item_id: str, local_path: str) -> str:
    """Upload `local_path` sous `<content_item_id>.mp4` (upsert : régénérer
    écrase la version précédente au même chemin). Retourne l'URL publique.
    Lève une exception si l'upload échoue — à l'appelant de décider s'il
    retombe sur le chemin local plutôt que de faire échouer tout le run."""
    storage_path = f"{content_item_id}.mp4"
    client.storage.from_(BUCKET).upload(
        storage_path,
        str(Path(local_path).resolve()),
        file_options={"content-type": "video/mp4", "upsert": "true"},
    )
    return client.storage.from_(BUCKET).get_public_url(storage_path)
