"""Worker de génération — traite la file de content_items en attente.

Le pipeline (ElevenLabs + ffmpeg) ne tourne pas sur Vercel : growthos-web
insère un content_item en status='queued' (script déjà construit par le
front, voir content/actions.ts `buildScript()`), ce worker le récupère,
génère la vidéo, et remet le statut à jour ('video' ou 'failed' + `error`).

Usage :
    python worker.py                  # boucle, poll toutes les 10s
    python worker.py --interval 5     # poll toutes les 5s
    python worker.py --once           # traite au plus un job puis s'arrête
                                       # (pratique derrière un cron externe)
"""
import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine import assembler, db, repo


def process_one(client) -> bool:
    """Réclame et traite un job de la file. Retourne True si un job a été
    traité (avec succès ou en échec), False si la file était vide."""
    item = repo.claim_queued_item(client)
    if not item:
        return False

    content_item_id = item["id"]
    print(f"\n=== Génération {content_item_id} ===")
    try:
        result = assembler.run_for_content_item(content_item_id)
        print(f"=== OK {content_item_id} : {result['video']} ===")
    except Exception as exc:
        print(f"=== ÉCHEC {content_item_id} : {exc} ===")
        traceback.print_exc()
        repo.mark_failed(client, content_item_id, str(exc))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=10.0, help="secondes entre deux polls quand la file est vide (défaut 10)")
    parser.add_argument("--once", action="store_true", help="traite au plus un job puis s'arrête")
    args = parser.parse_args()

    client = db.get_service_client()
    print(f"Worker GrowthOS démarré (poll toutes les {args.interval}s). Ctrl+C pour arrêter.")

    while True:
        try:
            processed = process_one(client)
        except KeyboardInterrupt:
            raise
        except Exception:
            # Erreur de connexion / requête réseau vers Supabase, pas un
            # échec de génération : on log et on continue plutôt que de
            # planter le worker.
            traceback.print_exc()
            processed = False

        if args.once:
            return
        if not processed:
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWorker arrêté.")
