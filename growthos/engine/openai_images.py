"""Image IA (OpenAI, `gpt-image-2.5-flare` par défaut) pour les visuels de scène,
voir `visuals.py` pour l'orchestration (regroupement par scène, repli Pexels)
et `image_model_router.py` pour le choix du modèle/qualité par usage.

Best effort, jamais bloquant : clé absente, erreur API, timeout... tout
retombe sur None, l'appelant (`visuals.fetch_block_images`) retombe alors sur
Pexels/fond uni pour ce bloc, comme si OpenAI n'existait pas. Ce contrat est
préservé par le retry/backoff ci-dessous : un échec DÉFINITIF (après
tentatives) reste un `None`, jamais une exception — rien en amont
(`engine/assembler.py`) n'attrape d'exception autour de cet appel.

Deux endpoints selon le besoin :

- `/v1/images/generations` (texte pur) — génération "final" d'une scène,
  indépendante des autres (voir `visuals.py` pour le pourquoi : dériver une
  scène de la précédente fige la pose).
- `/v1/images/edits` (image de référence + texte) — soit l'ancien chemin
  d'ancrage (`generate_image(reference_image_path=...)`, plus utilisé par
  défaut), soit `edit_image()` : correction CIBLÉE d'une image déjà générée
  ("corrige la main, garde tout le reste"), le vrai bon usage de cet endpoint.

Réglages via l'environnement (défauts raisonnables sinon) :
  OPENAI_IMAGE_MODEL    (défaut "gpt-image-2.5-flare" ; repli utilisé par
                         `image_model_router.select_model("final")` si
                         IMAGE_MODEL_PREMIUM n'est pas renseigné)
  OPENAI_IMAGE_QUALITY  ("low" | "medium" | "high" ; défaut "medium")

Retry : 3 tentatives, backoff exponentiel (2s, 4s) sur erreur réseau/429/5xx —
même pattern que `engine/tts.py`. Un 4xx autre (ex. rejet content-policy,
taille invalide) n'est PAS retenté : aucune chance qu'une nouvelle tentative
change le résultat, on classe l'erreur et on abandonne tout de suite.
"""
import base64
import os
import time
from pathlib import Path

import requests

GENERATIONS_URL = "https://api.openai.com/v1/images/generations"
EDITS_URL = "https://api.openai.com/v1/images/edits"

_DEFAULT_MODEL = "gpt-image-2.5-flare"
_DEFAULT_QUALITY = "medium"
_VALID_QUALITIES = {"low", "medium", "high", "auto"}

# Tailles supportées par gpt-image-1 / -mini ; la plus proche de chaque
# aspect_ratio du pipeline. 1024x1536 (2:3) est le format portrait le plus
# haut proposé — engine/video.py recadre ensuite en 1080x1920 (9:16) plein
# cadre, donc on demande volontairement le plus grand portrait disponible.
_SIZE_BY_RATIO = {"9:16": "1024x1536", "16:9": "1536x1024", "1:1": "1024x1024"}

_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_EDIT_PRESERVE_INSTRUCTION = (
    "Preserve everything that is already correct. Only modify the requested "
    "defect described below. Keep composition, camera angle, lighting, "
    "character identity and environment unchanged unless explicitly asked "
    "to change them.\n\n"
)


def _model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "").strip() or _DEFAULT_MODEL


def _quality() -> str:
    q = os.environ.get("OPENAI_IMAGE_QUALITY", "").strip().lower()
    return q if q in _VALID_QUALITIES else _DEFAULT_QUALITY


def _resolve_quality(quality: str | None) -> str:
    return quality if quality in _VALID_QUALITIES else _quality()


class GenerationError(Exception):
    """Interne — toujours attrapée par `generate_image`/`edit_image`, jamais
    propagée à l'appelant public (qui ne voit qu'un `None`)."""

    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind


def _classify_error(exc: Exception | None, status_code: int | None, body: str = "") -> str:
    """Catégorie d'échec pour le logging/diagnostic uniquement — n'affecte
    jamais le comportement (toujours best-effort côté appelant public)."""
    if exc is not None:
        return "timeout" if isinstance(exc, requests.Timeout) else "network"
    if status_code == 429:
        return "rate_limit"
    if status_code in (400, 415) and ("content_polic" in body.lower() or "safety" in body.lower()):
        return "content_policy"
    if status_code and 400 <= status_code < 500:
        return "invalid_request"
    if status_code and status_code >= 500:
        return "server_error"
    return "unknown"


def _post_with_retry(url: str, headers: dict, timeout: int, *, json_body=None, data=None, files=None):
    """POST avec retry/backoff (2s, 4s) sur réseau/429/5xx ; échec immédiat
    sur 4xx autre. Lève `GenerationError` — toujours attrapée par l'appelant."""
    last_kind = "unknown"
    last_detail = "raison inconnue"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(url, headers=headers, json=json_body, data=data, files=files, timeout=timeout)
        except requests.RequestException as exc:
            last_kind = _classify_error(exc, None)
            last_detail = str(exc)
        else:
            if resp.status_code == 200:
                return resp
            body = resp.text[:300]
            kind = _classify_error(None, resp.status_code, body)
            if resp.status_code not in _RETRYABLE_STATUS:
                raise GenerationError(kind, f"HTTP {resp.status_code} : {body}")
            last_kind, last_detail = kind, f"HTTP {resp.status_code} : {body}"

        if attempt < _MAX_ATTEMPTS:
            time.sleep(2 ** attempt)

    raise GenerationError(last_kind, f"échec après {_MAX_ATTEMPTS} tentatives — {last_detail}")


def _decode_and_write(resp, out_path: str) -> str:
    b64 = resp.json()["data"][0]["b64_json"]
    image_bytes = base64.b64decode(b64)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(image_bytes)
    return out_path


def generate_image(
    prompt: str,
    out_path: str,
    aspect_ratio: str = "9:16",
    reference_image_path: str | None = None,
    model: str | None = None,
    quality: str | None = None,
) -> str | None:
    """Génère une image et l'écrit sur `out_path` (JPEG). Retourne le chemin,
    ou None si pas de clé configurée ou échec définitif (ne lève jamais).

    `model`/`quality` : si fournis (voir `image_model_router.select_model`),
    priment sur `OPENAI_IMAGE_MODEL`/`OPENAI_IMAGE_QUALITY` — laissés à None,
    comportement identique à avant.

    Si `reference_image_path` pointe vers une image existante, on passe par
    `/v1/images/edits` : le modèle repart de cette image (même personnage,
    même style) au lieu de regénérer de zéro. Historique : ce chemin servait
    à l'ancrage scène-à-scène, abandonné (voir `visuals.py`) — gardé ici pour
    compatibilité, plus appelé par défaut."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    resolved_model = model or _model()
    resolved_quality = _resolve_quality(quality)
    size = _SIZE_BY_RATIO.get(aspect_ratio, "1024x1536")
    headers = {"Authorization": f"Bearer {api_key}"}
    # "high" peut prendre 30-60 s côté OpenAI, surtout via /edits.
    timeout = 180 if resolved_quality == "high" else 90

    use_reference = bool(reference_image_path and Path(reference_image_path).exists())

    try:
        if use_reference:
            data = {
                "model": resolved_model,
                "prompt": prompt,
                "size": size,
                "quality": resolved_quality,
                "n": "1",
                "output_format": "jpeg",
            }
            # Compatibilité gpt-image-1. GPT Image 2.5 traite déjà les entrées
            # avec une haute fidélité et n'accepte pas ce paramètre.
            if resolved_model == "gpt-image-1":
                data["input_fidelity"] = "high"
            with open(reference_image_path, "rb") as fh:  # type: ignore[arg-type]
                files = {"image": (Path(reference_image_path).name, fh, "image/jpeg")}
                resp = _post_with_retry(EDITS_URL, headers, timeout, data=data, files=files)
        else:
            resp = _post_with_retry(
                GENERATIONS_URL, headers, timeout,
                json_body={
                    "model": resolved_model,
                    "prompt": prompt,
                    "size": size,
                    "quality": resolved_quality,
                    "n": 1,
                    "output_format": "jpeg",
                },
            )
        return _decode_and_write(resp, out_path)
    except GenerationError as exc:
        print(f"       image IA : échec ({exc.kind}) — {exc}")
        return None
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
        print(f"       image IA : échec (unknown) — {exc}")
        return None


def edit_image(
    prompt: str,
    image_path: str,
    out_path: str,
    model: str | None = None,
    quality: str | None = None,
    aspect_ratio: str = "9:16",
) -> str | None:
    """Correction CIBLÉE d'une image déjà générée, via `/v1/images/edits`.
    `prompt` décrit uniquement le défaut à corriger (ex. "corrige la main
    droite, elle a un doigt en trop") — une instruction de préservation est
    automatiquement préfixée pour garder tout le reste (composition, angle,
    éclairage, identité du personnage, décor). Best-effort comme
    `generate_image` : jamais d'exception, `None` en cas d'échec."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not Path(image_path).exists():
        return None

    resolved_model = model or "gpt-image-2.5-flare"
    resolved_quality = quality if quality in _VALID_QUALITIES else "high"
    size = _SIZE_BY_RATIO.get(aspect_ratio, "1024x1536")
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = 180

    data = {
        "model": resolved_model,
        "prompt": _EDIT_PRESERVE_INSTRUCTION + prompt,
        "size": size,
        "quality": resolved_quality,
        "n": "1",
        "output_format": "jpeg",
    }
    if resolved_model == "gpt-image-1":
        data["input_fidelity"] = "high"

    try:
        with open(image_path, "rb") as fh:
            files = {"image": (Path(image_path).name, fh, "image/jpeg")}
            resp = _post_with_retry(EDITS_URL, headers, timeout, data=data, files=files)
        return _decode_and_write(resp, out_path)
    except GenerationError as exc:
        print(f"       image IA (edit) : échec ({exc.kind}) — {exc}")
        return None
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
        print(f"       image IA (edit) : échec (unknown) — {exc}")
        return None
