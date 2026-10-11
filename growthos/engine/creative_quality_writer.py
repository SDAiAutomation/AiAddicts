"""Opt-in atomic persistence through a reviewed Supabase RPC.

This function never uses a read-modify-write cycle or updates publication status.
The SQL function must be deployed separately after security review.
"""
from __future__ import annotations

from .creative_quality_persistence import prepare_report


def store_report(client, content_item_id: str, report: dict, *,
                 script_version: int, video_script_version: int | None = None,
                 current_version_id: str | None = None) -> bool:
    """Return False for a stale/missing content item; raise on RPC errors."""
    payload = prepare_report(report, script_version=script_version,
                             video_script_version=video_script_version,
                             current_version_id=current_version_id)
    response = client.rpc("store_creative_quality_report", {
        "p_content_item_id": content_item_id,
        "p_script_version": script_version,
        "p_video_script_version": video_script_version,
        "p_current_version_id": current_version_id,
        "p_report": payload,
    }).execute()
    if response.data is True:
        return True
    if response.data is False:
        return False
    raise RuntimeError("Unexpected quality persistence RPC result")
