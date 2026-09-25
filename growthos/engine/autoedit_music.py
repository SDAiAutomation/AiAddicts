"""Musique de fond AutoEdit pour les vidéos sans son.

Décision du 2026-09-25 (recherche : licences musicales, pratiques des
montages sportifs) : quand la source n'a pas de piste audio ou qu'elle est
quasi muette, on ajoute une musique ORIGINALE générée par Eleven Music,
taillée à la durée exacte du montage et accordée au style (Hype,
Cinématique, Épuré, Émotionnel). Une source qui a du son (public,
commentaire) garde son audio : on ne le remplace jamais automatiquement.

Pourquoi Eleven Music plutôt qu'une bibliothèque « libre de droits » : ses
conditions autorisent l'usage commercial en ligne sur les plans payants,
sans attribution, intégré à notre produit (seule la revente des morceaux
est interdite), alors que les licences des bibliothèques gratuites sont
floues pour un SaaS et exposent à de fausses réclamations Content ID.
La musique ne règle PAS les droits des images elles-mêmes.

Best-effort : une panne de génération n'empêche jamais le montage, elle
est signalée dans le rapport et les alertes qualité.
"""
import os
import re
from pathlib import Path

import requests

from engine.video import _run

MUSIC_URL = "https://api.elevenlabs.io/v1/music"
MUSIC_MODEL = "music_v1"
_DEFAULT_SILENCE_DB = -45.0
_FADE_OUT_SECONDS = 1.5

# Instrumental uniquement : pas de paroles qui couvriraient un futur
# commentaire, ni de risque de ressemblance avec une chanson connue.
STYLE_PROMPTS = {
    "hype": "Energetic instrumental sports highlight track, punchy drums, driving synth bass, "
            "rising build-ups and hard-hitting drops, around 128 BPM, stadium energy.",
    "cinematic": "Epic cinematic instrumental, orchestral strings and big percussion, "
                 "slow build to a powerful climax, trailer style, heroic sports mood.",
    "clean": "Modern minimal instrumental, light upbeat electronic groove, clean percussion, "
             "positive and focused, unobtrusive background for a sports montage.",
    "emotional": "Emotional instrumental, piano and soft strings, uplifting and hopeful, "
                 "gradual swell, reflective sports story mood.",
}


def music_enabled() -> bool:
    """Actif par défaut dès qu'une clé ElevenLabs est présente ;
    `AUTOEDIT_MUSIC=off` le coupe."""
    flag = os.environ.get("AUTOEDIT_MUSIC", "on").strip().lower()
    return flag not in {"0", "off", "false", "no"} and bool(os.environ.get("ELEVENLABS_API_KEY"))


def silence_threshold_db() -> float:
    try:
        return float(os.environ.get("AUTOEDIT_SILENCE_DB", "").strip() or _DEFAULT_SILENCE_DB)
    except ValueError:
        return _DEFAULT_SILENCE_DB


def mean_volume_db(path: str) -> float | None:
    """Volume moyen de la piste audio (ffmpeg volumedetect), None si illisible."""
    result = _run([
        "ffmpeg", "-i", str(Path(path).resolve()), "-vn", "-af", "volumedetect", "-f", "null", "-",
    ])
    match = re.search(r"mean_volume:\s*(-?(?:[0-9]+(?:\.[0-9]+)?|inf))\s*dB", result.stderr)
    if not match:
        return None
    raw = match.group(1)
    return -120.0 if raw in {"-inf", "inf"} else float(raw)


def silence_reason(path: str, has_audio: bool) -> str | None:
    """'no_audio' (pas de piste), 'silent' (piste quasi muette) ou None
    (la source a du son : on le garde)."""
    if not has_audio:
        return "no_audio"
    level = mean_volume_db(path)
    if level is not None and level < silence_threshold_db():
        return "silent"
    return None


def compose(style: str, seconds: float, output_path: str) -> str:
    """Génère une musique instrumentale de la durée demandée (min 3 s)."""
    response = requests.post(
        MUSIC_URL,
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
        json={
            "prompt": STYLE_PROMPTS.get(style, STYLE_PROMPTS["clean"]),
            "music_length_ms": int(max(3.0, seconds) * 1000),
            "model_id": MUSIC_MODEL,
            "force_instrumental": True,
        },
        timeout=240,
    )
    if not response.ok:
        raise RuntimeError(f"Eleven Music HTTP {response.status_code}: {response.text[:200]}")
    if not response.content:
        raise RuntimeError("Eleven Music a renvoyé un fichier vide")
    target = Path(output_path)
    target.write_bytes(response.content)
    return str(target)


def mux_music(video_path: str, music_path: str, output_path: str, seconds: float) -> str:
    """Remplace l'audio (absent ou muet) du montage par la musique, avec un
    fondu de sortie. La vidéo n'est pas réencodée."""
    fade_start = max(0.0, seconds - _FADE_OUT_SECONDS)
    _run([
        "ffmpeg", "-y", "-i", str(Path(video_path).resolve()), "-i", str(Path(music_path).resolve()),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-af", f"afade=t=in:d=0.3,afade=t=out:st={fade_start:.2f}:d={_FADE_OUT_SECONDS}",
        "-c:a", "aac", "-b:a", "160k", "-t", f"{seconds:.3f}", "-movflags", "+faststart",
        str(Path(output_path).resolve()),
    ])
    out = Path(output_path)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("FFmpeg n'a produit aucun montage avec musique")
    return str(out)


def cost_usd(seconds: float) -> float | None:
    """Coût estimé ; None si `AUTOEDIT_MUSIC_USD_PER_MIN` absent (jamais deviné)."""
    raw = os.environ.get("AUTOEDIT_MUSIC_USD_PER_MIN", "").strip()
    try:
        return round(float(raw) * seconds / 60, 4) if raw else None
    except ValueError:
        return None
