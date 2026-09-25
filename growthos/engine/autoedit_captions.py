"""Transcription Scribe et sous-titres mot par mot du profil AutoEdit general."""
import os
from pathlib import Path

import requests

from engine import captions
from engine.video import _run

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
SCRIBE_MODEL = "scribe_v2"
CAPTION_CANVAS = "1080x1920"


def transcribe(path: str) -> list[dict]:
    with open(path, "rb") as media:
        response = requests.post(
            SCRIBE_URL,
            headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
            files={"file": (Path(path).name, media, "application/octet-stream")},
            data={"model_id": SCRIBE_MODEL, "timestamps_granularity": "word", "tag_audio_events": "false"},
            timeout=300,
        )
    if not response.ok:
        raise RuntimeError(f"Eleven Scribe HTTP {response.status_code}: {response.text[:200]}")
    words = response.json().get("words") or []
    return [
        {"text": str(word["text"]).strip(), "start": float(word["start"]), "end": float(word["end"])}
        for word in words
        if word.get("type") == "word" and word.get("text") and word.get("start") is not None and word.get("end") is not None
    ]


def burn(video_path: str, words: list[dict], output_path: str, work_dir: str) -> str:
    if not words:
        return video_path
    duration = max(word["end"] for word in words)
    cues = captions.build_cues([(words, duration)])
    # Les tailles et marges des styles sont calibrées pour 1080x1920 (Generate).
    # On décrit donc le .ass dans ce repère : libass le met à l'échelle du
    # montage 720x1280. Déclarer 720x1280 grossissait le texte de 50 % (3
    # lignes pour 3 mots au lieu d'une, constaté le 2026-09-25).
    ass_path = captions.write_ass(cues, str(Path(work_dir) / "autoedit-captions.ass"), "word_pop", CAPTION_CANVAS)
    _run([
        "ffmpeg", "-y", "-i", str(Path(video_path).resolve()), "-vf", f"subtitles={Path(ass_path).name}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", "-movflags", "+faststart",
        str(Path(output_path).resolve()),
    ], cwd=work_dir)
    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError("FFmpeg n'a produit aucun montage sous-titre")
    return output_path


def cost_usd(seconds: float) -> float | None:
    raw = os.environ.get("AUTOEDIT_SCRIBE_USD_PER_HOUR", "").strip()
    try:
        return round(float(raw) * seconds / 3600, 4) if raw else None
    except ValueError:
        return None
