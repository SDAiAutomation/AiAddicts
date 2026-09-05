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
    python worker.py --until-idle     # traite tout ce qui est en file puis
                                       # s'arrête dès qu'elle est vide (pas de
                                       # sleep final) — pratique pour une
                                       # tâche planifiée à durée bornée
                                       # (GitHub Actions...) : file vide ->
                                       # sortie quasi immédiate au lieu
                                       # d'attendre le timeout du job.
"""
import argparse
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine import assembler, db, repo

if sys.platform == "win32":
    # La console Windows garde son ancien codepage (cp1252/cp850) par défaut,
    # qui ne sait pas encoder les accents des print() -> caractères "�". On
    # bascule la console elle-même en UTF-8 (chcp 65001) avant de reconfigurer
    # stdout/stderr pour écrire en UTF-8 : sans les deux à la fois, l'un des
    # deux côtés reste désaccordé et le mojibake persiste.
    subprocess.run(["chcp", "65001"], shell=True, capture_output=True)

# Sans ça, les print() peuvent rester bufferisés (redirection vers un fichier,
# terminal non interactif) et le worker paraît figé alors qu'il avance juste
# silencieusement en mémoire tampon.
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

_HEARTBEAT_EVERY = 60.0  # secondes entre deux rappels "toujours en attente"


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
        print(f"=== OK {content_item_id} : {result['video_url']} ===")
    except Exception as exc:
        print(f"=== ÉCHEC {content_item_id} : {exc} ===")
        traceback.print_exc()
        repo.mark_failed(client, content_item_id, str(exc))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interval", type=float, default=10.0, help="secondes entre deux polls quand la file est vide (défaut 10)")
    parser.add_argument("--once", action="store_true", help="traite au plus un job puis s'arrête")
    parser.add_argument(
        "--until-idle", action="store_true",
        help="traite tout ce qui est en file puis s'arrête dès qu'elle est vide, sans sleep final",
    )
    args = parser.parse_args()

    client = db.get_service_client()
    print(f"Worker GrowthOS démarré (poll toutes les {args.interval}s). Ctrl+C pour arrêter.")

    idle_since = time.monotonic()
    last_heartbeat = idle_since

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

        if processed:
            idle_since = time.monotonic()
            last_heartbeat = idle_since
        elif args.until_idle:
            print("File vide — arrêt (--until-idle).")
            return
        else:
            # File vide : rappel périodique que le worker tourne toujours et
            # attend un job, plutôt qu'un silence qu'on ne peut pas distinguer
            # d'un blocage.
            now = time.monotonic()
            if now - last_heartbeat >= _HEARTBEAT_EVERY:
                print(f"… en attente d'un job (file vide depuis {int(now - idle_since)}s)")
                last_heartbeat = now
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWorker arrêté.")
