"""Génération de la voix off via l'API ElevenLabs."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
REQUEST_TIMEOUT_SECONDS = 120


class TTSError(RuntimeError):
    pass


def generate_voiceover(
    text: str,
    voice_id: str,
    output_path: Path,
    api_key: Optional[str] = None,
) -> Path:
    """Génère un fichier mp3 de voix off pour le texte donné et le sauvegarde sur disque."""
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise TTSError("ELEVENLABS_API_KEY manquante (variable d'environnement non définie)")

    url = ELEVENLABS_API_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": DEFAULT_MODEL_ID,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise TTSError(
            f"Échec de la génération voix off (HTTP {response.status_code}) : {response.text[:500]}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path
