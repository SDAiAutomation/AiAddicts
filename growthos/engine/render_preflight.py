"""Optional, read-only ffprobe checks for rendered video.

Does not change publication status or invoke paid services.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


# Thresholds measured on 36 real renders (no false positive): the longest
# legitimate silence was 1.15 s (quiz pause), no freeze >= 2 s, mean volume
# between -17 and -27 dB. Black frames are NOT checked: dark Motion Graphics
# themes legitimately stay black for up to 7 s.
SILENCE_SECONDS = 2.5
FREEZE_SECONDS = 4.0
MIN_MEAN_VOLUME_DB = -38.0
_SILENCE_RE = re.compile(r"silence_duration: ([\d.]+)")
_FREEZE_RE = re.compile(r"freeze_duration: ([\d.]+)")
_FREEZE_START_RE = re.compile(r"freeze_start: ([\d.]+)")
_MEAN_RE = re.compile(r"mean_volume: (-?[\d.]+)")


def inspect_video(path: str, *, timeout_seconds: int = 15, av_timeout_seconds: int = 120) -> dict:
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
    if not issues:
        issues.extend(_av_issues(file, has_audio=audio is not None, duration=duration, timeout_seconds=av_timeout_seconds))
    return _report(issues, duration=duration, width=(video or {}).get("width"), height=(video or {}).get("height"))


def _av_issues(file: Path, *, has_audio: bool, duration: float, timeout_seconds: int) -> list[dict]:
    """One decoding pass (~10 % of the video length). Never blocks: heuristics only."""
    audio_filter = f"silencedetect=n=-35dB:d={SILENCE_SECONDS},volumedetect" if has_audio else "anull"
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(file),
             "-af", audio_filter, "-vf", f"freezedetect=n=-60dB:d={FREEZE_SECONDS}",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [_issue("av_check_unavailable", "Contrôle audio/vidéo indisponible (non vérifié).", "info",
                       confidence="unverified")]
    if result.returncode != 0:
        return [_issue("av_check_unavailable", "Contrôle audio/vidéo indisponible (non vérifié).", "info",
                       confidence="unverified")]
    log = result.stderr or ""
    issues = []
    silences = [float(x) for x in _SILENCE_RE.findall(log)]
    if silences:
        issues.append(_issue("long_silence", f"Silence de {max(silences):.1f} s détecté dans la narration.",
                             "warning", evidence=f"{len(silences)} silence(s) ≥ {SILENCE_SECONDS} s",
                             confidence="heuristic"))
    freezes = [float(x) for x in _FREEZE_RE.findall(log)]
    starts = [float(x) for x in _FREEZE_START_RE.findall(log)]
    if len(starts) > len(freezes):
        # A freeze lasting until the end of the file never prints freeze_duration.
        freezes.append(max(duration - starts[-1], FREEZE_SECONDS))
    if freezes:
        issues.append(_issue("frozen_video", f"Image figée pendant {max(freezes):.1f} s.",
                             "warning", evidence=f"{len(freezes)} passage(s) ≥ {FREEZE_SECONDS} s",
                             confidence="heuristic"))
    mean = _MEAN_RE.search(log)
    if mean and float(mean.group(1)) < MIN_MEAN_VOLUME_DB:
        issues.append(_issue("audio_too_quiet", f"Volume moyen très faible ({mean.group(1)} dB).",
                             "warning", confidence="heuristic"))
    return issues


def _issue(code: str, reason: str, severity: str, *, evidence: str = "",
           confidence: str = "deterministic") -> dict:
    return {
        "code": code, "severity": severity, "source": "render",
        "block_index": None, "evidence": evidence, "reason": reason,
        "suggested_action": "Inspecter et régénérer uniquement le rendu concerné.",
        "confidence": confidence,
    }


def _report(issues: list[dict], **metadata: object) -> dict:
    decision = "block" if any(i["severity"] == "blocking" for i in issues) else (
        "review" if any(i["severity"] == "warning" for i in issues) else "pass"
    )
    return {
        "schema_version": "creative_quality:v1", "stage": "render",
        "decision": decision, "issues": issues,
        "automatic_edits_applied": False, "enforcement_enabled": False,
        "metadata": metadata,
    }
