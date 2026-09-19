"""Génère la miniature (poster) des vidéos déjà rendues avant `poster_url`.

Sans poster, les listes affichent une icône. ffmpeg lit le premier frame
directement depuis l'URL publique (requêtes par plage : quelques centaines de
Ko par vidéo, pas le fichier entier).

`--faststart` remuxe en plus chaque MP4 (index de lecture en tête de fichier,
sans réencodage) et le ré-uploade. Ça télécharge et renvoie TOUTES les vidéos :
à lancer hors saturation du quota d'egress Supabase.

Usage :
    python scripts/backfill_posters.py --dry-run
    python scripts/backfill_posters.py
    python scripts/backfill_posters.py --faststart
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from engine import db, poster, repo, storage, trim
from engine.video import _run


def _remux_faststart(client, item_id: str, url: str, work: Path) -> str:
    src, out = work / "src.mp4", work / "faststart.mp4"
    trim._download(url, src)
    _run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(out)])
    return storage.upload_video(client, item_id, str(out))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="liste les vidéos concernées sans rien écrire")
    parser.add_argument("--faststart", action="store_true", help="remuxe aussi les MP4 (télécharge tout)")
    args = parser.parse_args()

    client = db.get_service_client()
    query = client.table("content_items").select("id, video_url, poster_url").like("video_url", "http%")
    if not args.faststart:
        query = query.is_("poster_url", "null")
    rows = query.execute().data or []
    print(f"{len(rows)} vidéo(s) à traiter")
    if args.dry_run:
        return

    done = failed = 0
    # ignore_cleanup_errors : sous Windows, le client de stockage peut garder un
    # fichier ouvert une fraction de seconde après l'upload.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for row in rows:
            item_id, url = row["id"], row["video_url"]
            work = Path(tmp) / item_id
            work.mkdir(parents=True, exist_ok=True)
            try:
                fields: dict = {}
                if args.faststart:
                    url = _remux_faststart(client, item_id, url, work)
                    fields["video_url"] = url
                if args.faststart or not row.get("poster_url"):
                    poster_path = poster.extract_poster(url, str(work / "poster.jpg"))
                    fields["poster_url"] = storage.upload_poster(client, item_id, poster_path)
                repo.update_content_item(client, item_id, **fields)
                done += 1
                print(f"  OK {item_id}")
            except Exception as exc:  # un fichier cassé ne doit pas bloquer les autres
                failed += 1
                print(f"  ÉCHEC {item_id} : {exc}")
    print(f"Terminé : {done} ok, {failed} échec(s)")


if __name__ == "__main__":
    main()
