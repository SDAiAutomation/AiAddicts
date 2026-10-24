"""Voices and final mix for animated stories (IO module: ElevenLabs with-timestamps + ffmpeg). Used only by the animated branch.

Same model and voice settings as `engine/tts.py` (read from it, never duplicated); the character alignment returned by the
provider drives the mouths. The key comes from the worker environment and is never logged.
"""
from __future__ import annotations

import array
import base64
import os
import subprocess
import time
import wave
from pathlib import Path

import requests

from .. import tts
from . import lipsync

FPS = 24
_ATTEMPTS = 3


def synthesize_line(text: str, voice_id: str, out_wav: Path) -> dict:
    """{"duration_s", "alignment", "envelope"} for one line; the voice is saved as a mono 44.1 kHz WAV."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY manquant")
    url = tts.ELEVENLABS_TTS_TIMESTAMPS_URL.format(voice_id=voice_id)
    payload = {"text": text, "model_id": tts.TTS_MODEL_ID, "voice_settings": dict(tts.TTS_VOICE_SETTINGS)}
    last = "unknown"
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            resp = requests.post(url, headers={"xi-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=60)
        except requests.RequestException as exc:
            last = f"network error: {type(exc).__name__}"
        else:
            if resp.status_code == 200:
                data = resp.json()
                break
            if resp.status_code != 429 and resp.status_code < 500:
                raise RuntimeError(f"voice provider refused the request (HTTP {resp.status_code})")
            last = f"HTTP {resp.status_code}"
        if attempt < _ATTEMPTS:
            time.sleep(2 * attempt)
    else:
        raise RuntimeError(f"voice provider unavailable after {_ATTEMPTS} attempts ({last})")
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    mp3 = out_wav.with_suffix(".mp3")
    mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ac", "1", "-ar", "44100", str(out_wav)], check=True, capture_output=True)
    with wave.open(str(out_wav)) as w:
        samples = array.array("h")
        samples.frombytes(w.readframes(w.getnframes()))
        rate = w.getframerate()
    envelope = lipsync.normalise(lipsync.rms_envelope(samples, rate, FPS))
    return {"duration_s": len(samples) / rate, "alignment": data["alignment"], "envelope": envelope}


def mix_and_mux(video: Path, starts: list, total: float, out_mp4: Path) -> Path:
    """Place every line at its start, normalise loudness and attach the result to the silent clip. (Music and sound
    effects are not part of this first version.)"""
    inputs, parts = [], []
    for i, (wav, start) in enumerate(starts):
        inputs += ["-i", str(wav)]
        ms = int(start * 1000)
        parts.append(f"[{i + 1}]adelay={ms}|{ms},loudnorm=I=-16:TP=-1.5[a{i}]")
    n = len(starts)
    mix = "".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total}[m]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), *inputs, "-filter_complex", ";".join(parts + [mix]), "-map", "0:v", "-map", "[m]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(total), str(out_mp4)]
    subprocess.run(cmd, check=True, capture_output=True)
    return Path(out_mp4)
