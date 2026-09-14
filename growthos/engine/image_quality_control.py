"""Contrôle qualité VISION d'une image générée — capacité NOUVELLE et
OPT-IN (`IMAGE_QC_ENABLED=false` par défaut, voir `.env.example`). Score
0-100 par dimension, décision APPROVE/EDIT/REGENERATE.

Jamais bloquant, même philosophie best-effort que `openai_images.py` : QC
désactivée, modèle non configuré, image absente, échec réseau ou réponse
malformée -> `None`. L'appelant (`engine/visuals.py`) traite `None` comme
"QC indisponible, image acceptée telle quelle" — jamais une erreur qui ferait
échouer la génération.

`IMAGE_QC_MODEL` n'a PAS de défaut codé en dur : vérifier qu'un modèle vision
donné est bien disponible (et à quel coût) sur le compte OpenAI utilisé est
la responsabilité de qui active cette capacité.
"""
import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import requests

CHAT_URL = "https://api.openai.com/v1/chat/completions"

_DEFAULT_THRESHOLD_APPROVE = 85
_DEFAULT_THRESHOLD_EDIT = 70
_DEFAULT_MAX_ATTEMPTS = 3

# Pondération du score global si le modèle ne renvoie pas overallScore
# lui-même (repli) — mêmes poids que le barème produit.
_WEIGHTS = {
    "visualQuality": 0.25,
    "characterConsistency": 0.20,
    "promptAdherence": 0.20,
    "composition": 0.15,
    "storyRelevance": 0.10,
    "technicalQuality": 0.10,
}
_SCORE_KEYS = tuple(_WEIGHTS.keys())

_QC_INSTRUCTIONS = (
    "Tu es un contrôle qualité pour des images cinématographiques de vidéos "
    "courtes (mystère, thriller psychologique, suspense). Évalue l'image "
    "jointe par rapport au prompt de scène et à la fiche personnage donnés. "
    "Réponds UNIQUEMENT en JSON, exactement cette forme : "
    '{"overallScore": <0-100>, "scores": {"visualQuality": <0-100>, '
    '"characterConsistency": <0-100>, "promptAdherence": <0-100>, '
    '"composition": <0-100>, "storyRelevance": <0-100>, '
    '"technicalQuality": <0-100>}, "issues": [<string>], '
    '"editInstructions": [<string>]}. "characterConsistency" : mets 100 si '
    "la scène ne contient aucun des personnages décrits (rien à comparer). "
    "editInstructions : liste vide si aucune correction n'est nécessaire, "
    "sinon des instructions courtes et ciblées (une par défaut à corriger)."
)


@dataclass(frozen=True)
class QCResult:
    approved: bool
    overall_score: int
    scores: dict
    issues: list
    recommended_action: str  # "APPROVE" | "EDIT" | "REGENERATE"
    edit_instructions: list = field(default_factory=list)


def qc_enabled() -> bool:
    return os.environ.get("IMAGE_QC_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def max_attempts() -> int:
    return max(1, _int_env("MAX_IMAGE_ATTEMPTS", _DEFAULT_MAX_ATTEMPTS))


def _decide(overall_score: int) -> str:
    approve_at = _int_env("IMAGE_QC_THRESHOLD_APPROVE", _DEFAULT_THRESHOLD_APPROVE)
    edit_at = _int_env("IMAGE_QC_THRESHOLD_EDIT", _DEFAULT_THRESHOLD_EDIT)
    if overall_score >= approve_at:
        return "APPROVE"
    if overall_score >= edit_at:
        return "EDIT"
    return "REGENERATE"


def _clamp_score(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def parse_qc_response(raw: dict) -> "QCResult | None":
    """Valide à la main le JSON retourné par le modèle vision (pas de
    `pydantic` — convention du repo, voir `engine/script.py`/`quality.py`).
    `None` si la forme est inexploitable : traité comme un échec de QC par
    l'appelant, jamais une exception."""
    if not isinstance(raw, dict):
        return None
    scores_raw = raw.get("scores")
    if not isinstance(scores_raw, dict):
        return None

    scores: dict = {}
    for key in _SCORE_KEYS:
        clamped = _clamp_score(scores_raw.get(key))
        if clamped is None:
            return None
        scores[key] = clamped

    overall_score = _clamp_score(raw.get("overallScore"))
    if overall_score is None:
        overall_score = round(sum(scores[k] * _WEIGHTS[k] for k in _SCORE_KEYS))

    issues_raw = raw.get("issues")
    issues = [str(i) for i in issues_raw] if isinstance(issues_raw, list) else []
    edit_raw = raw.get("editInstructions")
    edit_instructions = [str(i) for i in edit_raw] if isinstance(edit_raw, list) else []

    action = _decide(overall_score)
    return QCResult(
        approved=(action == "APPROVE"),
        overall_score=overall_score,
        scores=scores,
        issues=issues,
        recommended_action=action,
        edit_instructions=edit_instructions,
    )


def evaluate_image(image_path: str, scene_prompt: str, character_bible_text: str = "") -> "QCResult | None":
    """`None` si QC désactivée (`IMAGE_QC_ENABLED`), modèle non configuré
    (`IMAGE_QC_MODEL`), image absente, ou tout échec réseau/parsing — jamais
    d'exception, même best-effort que le reste du pipeline image."""
    if not qc_enabled():
        return None
    model = os.environ.get("IMAGE_QC_MODEL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not model or not api_key or not Path(image_path).exists():
        return None

    try:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
        user_text = (
            f"Prompt de la scène : {scene_prompt}\n\n"
            f"Fiche personnage attendue : {character_bible_text or '(aucun personnage récurrent sur cette vidéo)'}"
        )
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _QC_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        ],
                    },
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return parse_qc_response(json.loads(content))
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
        print(f"       QC image : échec ({exc}) — image acceptée telle quelle")
        return None
