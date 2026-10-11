"""Build a bounded, version-aware Creative Quality Gate persistence envelope.

Pure functions only: never writes to Supabase and never changes publication status.
The caller must enforce tenant authorization and atomic optimistic concurrency.
"""
from __future__ import annotations

from copy import deepcopy

MAX_ISSUES = 50
MAX_TEXT = 500


def prepare_report(report: dict, *, script_version: int, video_script_version: int | None = None) -> dict:
    if report.get("schema_version") != "creative_quality:v1":
        raise ValueError("Unsupported report version")
    if report.get("enforcement_enabled") is not False or report.get("automatic_edits_applied") is not False:
        raise ValueError("Only advisory reports may be persisted")
    if report.get("decision") not in ("pass", "review", "block"):
        raise ValueError("Invalid decision")
    if not isinstance(script_version, int) or isinstance(script_version, bool) or script_version < 0:
        raise ValueError("Invalid script version")
    if video_script_version is not None and (
        not isinstance(video_script_version, int) or isinstance(video_script_version, bool)
        or video_script_version < 0
    ):
        raise ValueError("Invalid rendered script version")
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        raise ValueError("Invalid issues")
    issues = []
    for raw in raw_issues[:MAX_ISSUES]:
        if not isinstance(raw, dict):
            continue
        if raw.get("severity") not in ("info", "warning", "blocking"):
            continue
        if raw.get("source") not in ("retention", "editorial", "render", "integrity"):
            continue
        index = raw.get("block_index")
        if index is not None and (type(index) is not int or index < 0):
            index = None
        issues.append({
            "code": str(raw.get("code") or "unknown")[:100],
            "severity": raw["severity"],
            "source": raw["source"],
            "block_index": index,
            "evidence": str(raw.get("evidence") or "")[:MAX_TEXT],
            "reason": str(raw.get("reason") or "")[:MAX_TEXT],
            "suggested_action": str(raw.get("suggested_action") or "")[:MAX_TEXT],
            "confidence": raw.get("confidence") if raw.get("confidence") in
                          ("deterministic", "heuristic", "unverified") else "unverified",
        })
    return {
        "schema_version": "creative_quality:v1",
        "stage": report.get("stage") if report.get("stage") in ("script", "render", "combined") else "combined",
        "decision": report["decision"],
        "issues": issues,
        "automatic_edits_applied": False,
        "enforcement_enabled": False,
        "script_version": script_version,
        "video_script_version": video_script_version,
        "issues_truncated": len(raw_issues) > MAX_ISSUES,
    }


def merge_score_details(score_details: dict, envelope: dict, *, current_script_version: int,
                        current_video_script_version: int | None) -> dict:
    """Merge in memory only after checking versions; DB update must still be atomic."""
    if envelope["script_version"] != current_script_version:
        raise ValueError("Stale script report")
    if envelope["video_script_version"] is not None and (
        envelope["video_script_version"] != current_video_script_version
    ):
        raise ValueError("Stale video report")
    if not isinstance(score_details, dict):
        raise ValueError("Invalid score_details")
    merged = deepcopy(score_details)
    merged["creative_quality"] = deepcopy(envelope)
    return merged
