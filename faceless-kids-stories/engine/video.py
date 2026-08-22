"""Génération des clips vidéo (style Studio 3D, Wan 2.2) via l'API queue de fal.ai."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import requests

FAL_MODEL_ID = "fal-ai/wan/v2.2-a14b/text-to-video"
FAL_QUEUE_BASE = "https://queue.fal.run"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600
SUBMIT_TIMEOUT_SECONDS = 60
POLL_REQUEST_TIMEOUT_SECONDS = 30
DOWNLOAD_TIMEOUT_SECONDS = 120

# Résolutions cibles par ratio d'aspect (vidéo courte format vertical par défaut).
ASPECT_RATIO_TO_SIZE = {
    "9:16": {"width": 720, "height": 1280},
    "16:9": {"width": 1280, "height": 720},
    "1:1": {"width": 960, "height": 960},
}


class VideoGenerationError(RuntimeError):
    pass


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}


def generate_video_clip(
    visual_prompt: str,
    style_prompt: str,
    aspect_ratio: str,
    output_path: Path,
    duration_seconds: float = 5.0,
    api_key: Optional[str] = None,
) -> Path:
    """Soumet une génération vidéo à fal.ai, attend le résultat et télécharge le mp4."""
    api_key = api_key or os.environ.get("FAL_KEY")
    if not api_key:
        raise VideoGenerationError("FAL_KEY manquante (variable d'environnement non définie)")

    size = ASPECT_RATIO_TO_SIZE.get(aspect_ratio, ASPECT_RATIO_TO_SIZE["9:16"])
    prompt = f"{style_prompt}. {visual_prompt}"

    payload = {
        "prompt": prompt,
        "image_size": size,
        "duration": max(1, round(duration_seconds)),
    }

    submit_resp = requests.post(
        f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}",
        headers=_headers(api_key),
        json=payload,
        timeout=SUBMIT_TIMEOUT_SECONDS,
    )
    if submit_resp.status_code not in (200, 201):
        raise VideoGenerationError(
            f"Échec de la soumission fal.ai (HTTP {submit_resp.status_code}) : {submit_resp.text[:500]}"
        )

    submission = submit_resp.json()
    status_url = submission.get("status_url")
    response_url = submission.get("response_url")
    if not status_url or not response_url:
        raise VideoGenerationError(f"Réponse fal.ai inattendue lors de la soumission : {submission}")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    status = None
    while time.monotonic() < deadline:
        status_resp = requests.get(status_url, headers=_headers(api_key), timeout=POLL_REQUEST_TIMEOUT_SECONDS)
        status_resp.raise_for_status()
        status = status_resp.json().get("status")
        if status == "COMPLETED":
            break
        if status in ("ERROR", "FAILED"):
            raise VideoGenerationError(f"Génération vidéo fal.ai échouée : {status_resp.text[:500]}")
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        raise VideoGenerationError(
            f"Délai d'attente dépassé ({POLL_TIMEOUT_SECONDS}s) pour la génération vidéo fal.ai "
            f"(dernier statut : {status})"
        )

    result_resp = requests.get(response_url, headers=_headers(api_key), timeout=POLL_REQUEST_TIMEOUT_SECONDS)
    result_resp.raise_for_status()
    result = result_resp.json()

    video_url = (result.get("video") or {}).get("url")
    if not video_url:
        raise VideoGenerationError(f"Aucune URL vidéo dans la réponse fal.ai : {result}")

    video_resp = requests.get(video_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
    video_resp.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(video_resp.content)
    return output_path
