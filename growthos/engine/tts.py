"""Voiceover generation via the ElevenLabs API."""
import json
import os
import subprocess
from pathlib import Path

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize(text: str, voice_id: str, out_path: str, api_key: str | None = None) -> str:
    """Render `text` to an mp3 file at `out_path`. Returns out_path."""
    api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY manquant (variable d'environnement ou .env)")

    resp = requests.post(
        ELEVENLABS_TTS_URL.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"échec ElevenLabs ({resp.status_code}) : {resp.text[:300]}")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(resp.content)
    return out_path


def get_duration_seconds(audio_path: str) -> float:
    """Read a media file's duration with ffprobe. Raises if ffprobe/ffmpeg is missing."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", audio_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])
