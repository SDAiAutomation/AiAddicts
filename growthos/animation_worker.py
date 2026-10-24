"""Dedicated worker for animated Story Studio jobs (experimental; run by .github/workflows/story-animation-worker.yml).

It exits at once unless STORY_ANIMATION_ENABLED is on, and it only ever claims animated stories: Standard and Quiz stay
with `worker.py`, which still refuses animated stories because it never receives the flag.

  python animation_worker.py --until-idle
"""
import argparse
import time
import traceback

from dotenv import load_dotenv

load_dotenv()

from engine import assembler, db, events, repo  # noqa: E402
from engine.story_animation import claim, contract  # noqa: E402


def process_one(client) -> bool:
    """Claim and run one animated job. True if one was handled (success or failure), False if none was queued."""
    item = claim.claim_animated_item(client)
    if not item:
        return False
    content_item_id = item["id"]
    print(f"\n=== Animation {content_item_id} ===")
    try:
        result = assembler.run_for_content_item(content_item_id)
        print(f"=== OK {content_item_id} : {result['video_url']} ===")
    except Exception as exc:  # noqa: BLE001 - one failed job must never stop the queue
        print(f"=== ÉCHEC {content_item_id} : {exc} ===")
        traceback.print_exc()
        repo.mark_failed(client, content_item_id, str(exc))
        events.record(client, "generation_failed", content_item_id, events.organization_id_of(client, content_item_id), error=str(exc)[:300])
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--until-idle", action="store_true", help="process everything queued, then stop")
    parser.add_argument("--once", action="store_true", help="process at most one job")
    args = parser.parse_args()
    if not contract.animation_enabled():
        print("STORY_ANIMATION_ENABLED is off: nothing is claimed.")
        return 0
    client = db.get_service_client()
    while True:
        processed = process_one(client)
        if args.once or (not processed and args.until_idle):
            return 0
        if not processed:
            time.sleep(10.0)


if __name__ == "__main__":
    raise SystemExit(main())
