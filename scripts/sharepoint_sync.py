#!/usr/bin/env python3
"""CLI: Start the SharePoint polling sync daemon (Phase 2).

Requires SP_TENANT_ID, SP_CLIENT_ID, SP_CLIENT_SECRET, SP_SITE_URL in .env

Usage:
    python scripts/sharepoint_sync.py
    python scripts/sharepoint_sync.py --once   # run one cycle and exit
"""
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sharepoint.sync import SharePointSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="SharePoint FI sync daemon")
    parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit")
    args = parser.parse_args()

    from config.settings import settings
    if not all([settings.sp_tenant_id, settings.sp_client_id, settings.sp_client_secret]):
        print("ERREUR : Variables SharePoint manquantes dans .env")
        print("  SP_TENANT_ID, SP_CLIENT_ID, SP_CLIENT_SECRET sont requises.")
        sys.exit(1)

    sync = SharePointSync()

    if args.once:
        sync.initialize()
        n = sync.sync_once()
        print(f"Sync terminé : {n} document(s) traité(s).")
    else:
        sync.run()


if __name__ == "__main__":
    main()
