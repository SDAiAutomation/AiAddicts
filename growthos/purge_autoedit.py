"""Supprime la source et les rendus des jobs AutoEdit arrivés à expiration
(`autoedit_jobs.expires_at`, posé par le worker à la fin du job,
AUTOEDIT_RETENTION_DAYS jours). Le job reste en base comme historique.

Lancé chaque jour par `.github/workflows/growthos-metrics.yml` — que
AutoEdit soit activé ou non : les vidéos déjà envoyées doivent disparaître
à la date promise même si la fonctionnalité est coupée entre-temps.

Usage:
    python purge_autoedit.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine import autoedit_repo, db


def main() -> int:
    purged = autoedit_repo.purge_expired(db.get_service_client())
    print(f"AutoEdit : {purged} job(s) purgé(s) (source et rendus supprimés).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
