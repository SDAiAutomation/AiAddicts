"""Image IA (OpenAI, `gpt-image-1-mini` par défaut) pour les visuels de scène,
voir `visuals.py` pour l'orchestration (regroupement par scène, repli Pexels).

Best effort, jamais bloquant : clé absente, erreur API, timeout... tout
retombe sur None, l'appelant (`visuals.fetch_block_images`) retombe alors sur
Pexels/fond uni pour ce bloc, comme si OpenAI n'existait pas.

Deux endpoints selon le besoin :

- `/v1/images/generations` (texte pur) — pour la première scène, qui fixe
  l'apparence des personnages à partir de la fiche personnage du script.
- `/v1/images/edits` (image de référence + texte) — pour les scènes
  suivantes : on repart de l'image de la scène 1 (`reference_image_path`)
  au lieu de zéro, avec `input_fidelity=high`, ce qui garde le même
  personnage / le même style d'une scène à l'autre. C'est le principal
  garde-fou contre la dérive « l'ourson devient un petit garçon » quand le
  prénom sonne humain.

Réglages via l'environnement (défauts raisonnables sinon) :
  OPENAI_IMAGE_MODEL    (défaut "gpt-image-1-mini" ; "gpt-image-1" pour la
                         meilleure adhérence au prompt, ~x3-4 le coût)
  OPENAI_IMAGE_QUALITY  ("low" | "medium" | "high" ; défaut "high")
"""
import base64
import os
from pathlib import Path

import requests

GENERATIONS_URL = "https://api.openai.com/v1/images/generations"
EDITS_URL = "https://api.openai.com/v1/images/edits"

_DEFAULT_MODEL = "gpt-image-1-mini"
_DEFAULT_QUALITY = "high"  # fidélité maximale ; ~0,05-0,08 $/image en mini
_VALID_QUALITIES = {"low", "medium", "high", "auto"}

# Tailles supportées par gpt-image-1 / -mini ; la plus proche de chaque
# aspect_ratio du pipeline. 1024x1536 (2:3) est le format portrait le plus
# haut proposé — engine/video.py recadre ensuite en 1080x1920 (9:16) plein
# cadre, donc on demande volontairement le plus grand portrait disponible.
_SIZE_BY_RATIO = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}


def _model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "").strip() or _DEFAULT_MODEL


def _quality() -> str:
    q = os.environ.get("OPENAI_IMAGE_QUALITY", "").strip().lower()
    return q if q in _VALID_QUALITIES else _DEFAULT_QUALITY


def generate_image(
    prompt: str,
    out_path: str,
    aspect_ratio: str = "9:16",
    reference_image_path: str | None = None,
) -> str | None:
    """Génère une image et l'écrit sur `out_path` (JPEG). Retourne le chemin,
    ou None si pas de clé configurée ou échec (ne lève jamais).

    Si `reference_image_path` pointe vers une image existante, on passe par
    `/v1/images/edits` : le modèle repart de cette image (même personnage,
    même style) au lieu de regénérer de zéro."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    model = _model()
    size = _SIZE_BY_RATIO.get(aspect_ratio, "1024x1536")
    quality = _quality()
    headers = {"Authorization": f"Bearer {api_key}"}
    # "high" peut prendre 30-60 s côté OpenAI, surtout via /edits.
    timeout = 180 if quality == "high" else 90

    use_reference = bool(reference_image_path and Path(reference_image_path).exists())

    try:
        if use_reference:
            data = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "n": "1",
                "output_format": "jpeg",
            }
            # `input_fidelity=high` garde fidèlement les traits de l'image de
            # référence (personnage, palette) — mais n'existe que sur le
            # modèle complet, pas sur -mini (400 sinon).
            if model == "gpt-image-1":
                data["input_fidelity"] = "high"
            with open(reference_image_path, "rb") as fh:  # type: ignore[arg-type]
                resp = requests.post(
                    EDITS_URL,
                    headers=headers,
                    data=data,
                    files={"image": (Path(reference_image_path).name, fh, "image/jpeg")},
                    timeout=timeout,
                )
        else:
            resp = requests.post(
                GENERATIONS_URL,
                headers=headers,
                json={
                    "model": model,
                    "prompt": prompt,
                    "size": size,
                    "quality": quality,
                    "n": 1,
                    "output_format": "jpeg",
                },
                timeout=timeout,
            )
        resp.raise_for_status()
        b64 = resp.json()["data"][0]["b64_json"]
        image_bytes = base64.b64decode(b64)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(image_bytes)
        return out_path
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError):
        return None
