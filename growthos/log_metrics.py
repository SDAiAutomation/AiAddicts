"""Log a weekly metrics snapshot for a published content item.

Usage:
    python log_metrics.py <content_item_id> --views 1200 --watch-time-pct 45.5 \\
        --likes 30 --comments 5 --shares 2 --followers-delta 8 --leads 3 \\
        [--mark-published]

Replaces the old metrics/suivi-hebdo.csv flat file: rows now live in
content_performance, joined to the content_items row the pipeline created.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine import db, repo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content_item_id")
    parser.add_argument("--views", type=int)
    parser.add_argument("--watch-time-pct", type=float, dest="watch_time_pct")
    parser.add_argument("--likes", type=int)
    parser.add_argument("--comments", type=int)
    parser.add_argument("--shares", type=int)
    parser.add_argument("--followers-delta", type=int, dest="followers_delta")
    parser.add_argument("--leads", type=int)
    parser.add_argument(
        "--mark-published", action="store_true",
        help="also set the content item's status to 'published' (first log after posting)",
    )
    args = parser.parse_args()

    client = db.get_service_client()

    if args.mark_published:
        repo.mark_published(client, args.content_item_id)
        print(f"content_item {args.content_item_id} marqué publié.")

    performance_id = repo.log_performance(
        client, args.content_item_id,
        views=args.views, watch_time_pct=args.watch_time_pct,
        likes=args.likes, comments=args.comments, shares=args.shares,
        followers_delta=args.followers_delta, leads=args.leads,
    )
    print(f"Métriques enregistrées : {performance_id}")


if __name__ == "__main__":
    main()
