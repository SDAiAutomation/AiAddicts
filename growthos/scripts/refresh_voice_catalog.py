"""Refresh the user-facing ElevenLabs voice catalogue without generating audio.

Usage: python scripts/refresh_voice_catalog.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "config" / "voice_catalog.json"
URL = "https://api.elevenlabs.io/v1/voices"


def normalize_voice(voice: dict) -> dict:
    labels = voice.get("labels") or {}
    return {
        "voice_id": voice["voice_id"],
        "name": voice["name"],
        "language": labels.get("language") or "unknown",
        "category": voice.get("category"),
        "gender": labels.get("gender"),
        "accent": labels.get("accent"),
        "age": labels.get("age"),
        "use_case": labels.get("use_case"),
        "descriptive": labels.get("descriptive"),
        "description": voice.get("description"),
        "preview_url": voice.get("preview_url"),
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY manquante")
    response = requests.get(URL, headers={"xi-api-key": key}, timeout=30)
    response.raise_for_status()
    voices = [normalize_voice(voice) for voice in response.json()["voices"]]
    if not voices or len({voice["voice_id"] for voice in voices}) != len(voices):
        raise ValueError("Catalogue ElevenLabs vide ou avec des voice_id dupliqués")
    voices.sort(key=lambda voice: (
        0 if voice["language"] == "fr" else 1 if voice["language"] == "en" else 2,
        voice["name"].casefold(),
    ))
    snapshot = {
        "source": "ElevenLabs GET /v1/voices",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "voices": voices,
    }
    temporary = DESTINATION.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(DESTINATION)
    print(f"{len(voices)} voix enregistrées dans {DESTINATION}")


if __name__ == "__main__":
    main()
