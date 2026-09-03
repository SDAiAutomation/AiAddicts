"""Voiceover generation via the ElevenLabs API."""
import json
import os
import subprocess
import time
from pathlib import Path

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_MAX_ATTEMPTS = 3


def synthesize(text: str, voice_id: str, out_path: str, api_key: str | None = None) -> str:
    """Render `text` to an mp3 file at `out_path`. Returns out_path.

    Retries transient failures (network errors, HTTP 429 / 5xx) with an
    exponential backoff; fails fast on other 4xx (bad voice_id, quota, auth).
    """
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY manquant (variable d'environnement ou .env)")

    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    last_error = "raison inconnue"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_error = f"erreur réseau : {exc}"
        else:
            if resp.status_code == 200:
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(resp.content)
                return out_path
            detail = f"HTTP {resp.status_code} : {resp.text[:300]}"
            if resp.status_code != 429 and resp.status_code < 500:
                raise RuntimeError(f"échec ElevenLabs, {detail}")
            last_error = detail

        if attempt < _MAX_ATTEMPTS:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"échec ElevenLabs après {_MAX_ATTEMPTS} tentatives — {last_error}")


def get_duration_seconds(audio_path: str) -> float:
    """Read a media file's duration with ffprobe. Raises if ffprobe is missing."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", audio_path,
            ],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "'ffprobe' introuvable — installe ffmpeg "
            "(apt install ffmpeg / brew install ffmpeg / winget install ffmpeg)"
        ) from exc
    return float(json.loads(result.stdout)["format"]["duration"])
