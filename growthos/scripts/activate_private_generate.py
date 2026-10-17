"""Activate private Generate storage AFTER deploying both web and worker fixes.

Read-only unless --activate --web-verified --worker-verified are all supplied.
Use the Storage API rather than editing storage's internal tables directly.
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.db import get_service_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--web-verified", action="store_true")
    parser.add_argument("--worker-verified", action="store_true")
    args = parser.parse_args()
    if args.activate and not (args.web_verified and args.worker_verified):
        parser.error("Deploy and verify both web and worker before activation.")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    storage = get_service_client().storage
    bucket = storage.get_bucket("content-videos")
    print(f"content-videos public={bucket.public}")
    if not args.activate:
        print("Read-only. No change applied.")
        return
    storage.update_bucket("content-videos", {"public": False})
    if storage.get_bucket("content-videos").public:
        raise RuntimeError("Private storage activation was not confirmed.")
    print("Private storage confirmed. Verify old public links, signed playback and downloads.")


if __name__ == "__main__":
    main()
