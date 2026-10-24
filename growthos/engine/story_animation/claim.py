"""Claim only animated stories from the queue (used by the dedicated animation worker; the main worker is untouched).

Same contract as `repo.claim_queued_item`: oldest first, and the claim is a conditional update on status = 'queued' so that
two workers can never take the same item. Everything else in the queue is left alone for the main worker.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import repo
from . import contract

WINDOW = 200  # queued rows inspected per claim; animated items are filtered in Python, not by a JSON path query


def claim_animated_item(client) -> dict | None:
    reclaimed = repo.reclaim_stale_generating_items(client)
    if reclaimed:
        print(f"       {reclaimed} item(s) 'generating' orphelin(s) remis en file")
    queued = (
        client.table("content_items").select("id, script").eq("status", "queued").order("created_at").limit(WINDOW).execute()
    )
    for row in queued.data or []:
        if not contract.is_animated(row.get("script")):
            continue
        won = (
            client.table("content_items")
            .update({"status": "generating", "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", row["id"])
            .eq("status", "queued")
            .execute()
        )
        if won.data:
            return row
    return None
