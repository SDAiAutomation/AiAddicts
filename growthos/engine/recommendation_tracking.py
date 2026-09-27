"""Verify signed generation receipts and report observations, never causal lift.

Contract: RECOMMENDATION_CONTRACT.md. No model call and no paid retry here.
"""
import base64
import hashlib
import hmac
import json
import math
import os
from datetime import datetime, timezone

from . import story_features

PURPOSE = "faceloop-recommendation:v1:"
VERSION = 1


def _object(value):
    return value if isinstance(value, dict) else {}


def script_fingerprint(script: dict) -> str:
    """Shared with growthos-web/lib/recommendation-receipt.ts (ordered strings)."""
    def text(value):
        return str(value or "").strip()
    quiz = script.get("quiz") or {}
    is_quiz = script.get("content_format") == "quiz"
    parts = [text(script.get("title")), "quiz" if is_quiz else "standard"]
    if is_quiz:
        parts.extend([text(quiz.get("topic")), text(quiz.get("intro")), text(quiz.get("outro"))])
        for question in quiz.get("questions") or []:
            parts.extend([text(question.get("question")), *map(text, question.get("choices") or []),
                          str(question.get("correct_choice", 0)), text(question.get("explanation"))])
    else:
        for block in script.get("blocks") or []:
            if text(block.get("text")):
                parts.extend([text(block.get("role")), text(block.get("text")), text(block.get("visual"))])
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def read_receipt(token, account_id: str) -> dict | None:
    secret = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not secret or not isinstance(token, str) or len(token) > 250_000:
        return None
    try:
        payload, signature = token.split(".")
        expected = base64.urlsafe_b64encode(hmac.new(secret.encode(), (PURPOSE + payload).encode(), hashlib.sha256).digest()).decode().rstrip("=")
        if not hmac.compare_digest(signature, expected):
            return None
        receipt = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if receipt.get("version") != VERSION or receipt.get("account_id") != account_id:
            return None
        if not isinstance(receipt.get("recommendation"), dict) or not receipt.get("generation_id"):
            return None
        return receipt
    except (ValueError, TypeError, UnicodeError, AttributeError):
        return None


def report_fingerprint(script: dict) -> str:
    parts = [script_fingerprint(script), str(script.get("visual_style") or "default"),
             str(script.get("caption_style") or "bold_stroke")]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def assess_application(script: dict, experiment: dict | None, features: dict | None) -> dict:
    experiment = _object(experiment)
    features = _object(features)
    if not experiment or experiment.get("version") != VERSION:
        return {"status": "needs_review", "reason": "unstructured_recommendation"}
    target = _object(experiment.get("target"))
    kind, label = target.get("kind"), target.get("label")
    if not label or target.get("direction") not in ("favor", "avoid"):
        return {"status": "needs_review", "reason": "invalid_target"}
    observed = None
    method = None
    if kind == "format":
        observed = " · ".join([str(script.get("content_format") or "standard"),
                               str(script.get("visual_style") or "default"),
                               str(script.get("caption_style") or "bold_stroke")])
        method = "saved_settings_v1"
    elif (features and features.get("version") == story_features.VERSION
          and features.get("input_fingerprint") == script_fingerprint(script)):
        observed = features.get("archetype" if kind == "archetype" else "hookType") if kind in ("archetype", "hook") else None
        method = f"story_features_v{story_features.VERSION}"
    if observed in (None, "autre", ""):
        return {"status": "needs_review", "reason": "classification_unavailable"}
    matched = observed == label
    if target["direction"] == "avoid":
        matched = not matched
    return {"status": "consistent" if matched else "not_observed", "observed": observed,
            "method": method, "reason": "diagnostic_not_proof"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def build_report(item: dict, rows: list[dict]) -> dict | None:
    script = item.get("script") or {}
    token = script.get("recommendation_receipt")
    if not token:
        return None
    fingerprint = script_fingerprint(script)
    receipt = read_receipt(token, str(item["account_id"]))
    base = {"version": VERSION, "script_fingerprint": fingerprint, "report_fingerprint": report_fingerprint(script),
            "evaluated_at": datetime.now(timezone.utc).isoformat(), "causal": False}
    if not receipt:
        return {**base, "application": {"status": "needs_review", "reason": "invalid_receipt"},
                "outcome": {"status": "unavailable"}}
    snapshot = receipt["recommendation"]
    experiment = _object(snapshot.get("experiment"))
    baseline = _object(experiment.get("baseline"))
    application = assess_application(script, experiment, item.get("story_features"))
    outcome = {"status": "awaiting_metrics", "metric": "watch_time_pct", "comparison": "historical_descriptive"}
    # Use the latest snapshot, not an older convenient one; absent values stay
    # absent. Measurements must belong to this content, account and generation.
    own = [r for r in rows if str(r.get("content_item_id")) == str(item["id"])
           and (r.get("content_items") or {}).get("account_id") == item["account_id"]]
    latest = max(own, key=lambda r: str(r.get("captured_at") or ""), default=None)
    if latest:
        views, retention = latest.get("views"), latest.get("watch_time_pct")
        # Supabase's numeric column is normally a float; tolerate decimal strings.
        try:
            retention = float(retention) if retention is not None else None
        except (ValueError, TypeError):
            retention = None
        minimum_views = 50
        outcome.update({"views": views if _number(views) else None,
                        "retention": retention if _number(retention) else None,
                        "captured_at": latest.get("captured_at"), "minimum_views": minimum_views})
        if not _number(views) or not _number(retention):
            outcome["status"] = "missing_metrics"
        elif (not _timestamp(latest.get("captured_at")) or not _timestamp(receipt.get("generated_at"))
              or _timestamp(latest["captured_at"]) < _timestamp(receipt["generated_at"])):
            outcome["status"] = "predates_generation"
        elif (item.get("video_script_version") is not None
              and item.get("script_version") != item["video_script_version"]):
            outcome["status"] = "script_changed_since_render"
        elif views < minimum_views:
            outcome["status"] = "insufficient_views"
        elif any(str(_object(s).get("content_item_id")) == str(item["id"]) for s in baseline.get("sources") or []):
            outcome["status"] = "baseline_overlap"
        elif (not _number(baseline.get("value")) or not _number(baseline.get("sample_size"))
              or baseline["sample_size"] < 3):
            outcome["status"] = "baseline_unavailable"
        else:
            outcome.update({"status": "observed", "baseline_retention": baseline["value"],
                            "baseline_sample_size": baseline["sample_size"],
                            "difference_points": round(retention - baseline["value"], 2)})
    return {**base, "generation_id": receipt["generation_id"],
            "recommendation_id": snapshot.get("id"), "recommendation_generated_at": snapshot.get("generated_at"),
            "hypothesis": experiment.get("hypothesis"),
            "edited_since_generation": fingerprint != receipt.get("script_fingerprint"),
            "application": application, "outcome": outcome}
