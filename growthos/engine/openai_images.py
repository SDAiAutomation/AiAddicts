"""Image IA (OpenAI, `gpt-image-1-mini`) pour le bloc hook uniquement — le
reste des blocs reste sur Pexels (gratuit), voir `visuals.py`. Le hook est le
seul bloc qui justifie le coût : c'est lui qui décide si quelqu'un reste.

Best effort, jamais bloquant : clé absente, erreur API, timeout... tout
retombe sur None, l'appelant (`visuals.fetch_block_images`) retombe alors sur
Pexels/fond uni pour ce bloc, comme si OpenAI n'existait pas.

Contrairement à Higgsfield (soumission + poll asynchrone, abandonné suite à
un blocage de modèle côté compte — voir git history), l'API Images d'OpenAI
est synchrone : un seul appel HTTP, réponse en base64 (`b64_json`), pas de
round-trip supplémentaire pour télécharger le résultat.
"""
import base64
import os
from pathlib import Path

import requests

API_URL = "https://api.openai.com/v1/images/generations"
_MODEL = "gpt-image-1-mini"
_QUALITY = "low"  # coût minimal (~0,005-0,01 $/image) — suffisant pour un fond de bloc

# Tailles supportées par gpt-image-1-mini ; la plus proche de chaque aspect_ratio du pipeline.
_SIZE_BY_RATIO = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}


def generate_image(prompt: str, out_path: str, aspect_ratio: str = "9:16") -> str | None:
    """Génère une image et l'écrit sur `out_path`. Retourne le chemin, ou
    None si pas de clé configurée ou échec (ne lève jamais)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        resp = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": _MODEL,
                "prompt": prompt,
                "size": _SIZE_BY_RATIO.get(aspect_ratio, "1024x1536"),
                "quality": _QUALITY,
                "n": 1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        b64 = resp.json()["data"][0]["b64_json"]
        image_bytes = base64.b64decode(b64)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(image_bytes)
        return out_path
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None
