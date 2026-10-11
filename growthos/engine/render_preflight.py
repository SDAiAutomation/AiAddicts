"""Optional, read-only ffprobe checks for rendered video.

Does not change publication status or invoke paid services.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def inspect_video(path: str, *, timeout_seconds: int = 15) -> dict:
    issues: list[dict] = []
    file = Path(path)
    if not file.is_file():
        return _report([_issue("render_missing", "Fichier vidéo introuvable.", "blocking")])
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height",
             "-of", "json", str(file)],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _report([_issue("probe_unavailable", f"ffprobe indisponible : {type(exc).__name__}.", "warning")])
    if result.returncode != 0:
        return _report([_issue("probe_failed", "Impossible d'analyser le conteneur vidéo.", "warning")])
    try:
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams") or []
        duration = float((metadata.get("format") or {}).get("duration") or 0)
    except (ValueError, TypeError, AttributeError):
        return _report([_issue("probe_invalid", "Métadonnées ffprobe invalides.", "warning")])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        issues.append(_issue("video_stream_missing", "Aucune piste vidéo détectée.", "blocking"))
    if audio is None:
        issues.append(_issue("audio_stream_missing", "Aucune piste audio détectée.", "blocking"))
    if duration <= 0:
        issues.append(_issue("duration_invalid", "Durée vidéo absente ou invalide.", "blocking"))
    if video and (int(video.get("width") or 0) <= 0 or int(video.get("height") or 0) <= 0):
        issues.append(_issue("dimensions_invalid", "Dimensions vidéo invalides.", "blocking"))
    return _report(issues, duration=duration, width=(video or {}).get("width"), height=(video or {}).get("height"))


def _issue(code: str, reason: str, severity: str) -> dict:
    return {
        "code": code, "severity": severity, "source": "render",
        "block_index": None, "evidence": "", "reason": reason,
        "suggested_action": "Inspecter et régénérer uniquement le rendu concerné.",
        "confidence": "deterministic",
    }


def _report(issues: list[dict], **metadata: object) -> dict:
    decision = "block" if any(i["severity"] == "blocking" for i in issues) else (
        "review" if issues else "pass"
    )
    return {
        "schema_version": "creative_quality:v1", "stage": "render",
        "decision": decision, "issues": issues,
        "automatic_edits_applied": False, "enforcement_enabled": False,
        "metadata": metadata,
    }
