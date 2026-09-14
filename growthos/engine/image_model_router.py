"""Sélection du modèle/qualité OpenAI Images par usage (preview/final/edit) +
estimation de coût. Voir `engine/openai_images.py` pour l'appel API réel et
`engine/visuals.py` pour l'orchestration qui appelle `select_model`.

Défauts pensés pour NE RIEN changer au comportement/coût actuel : une
installation qui ne renseigne aucune des nouvelles variables ci-dessous garde
exactement le même modèle/qualité qu'avant (celles de `OPENAI_IMAGE_MODEL`/
`OPENAI_IMAGE_QUALITY`) pour le mode "final", qui est le seul utilisé
aujourd'hui par `visuals.fetch_block_images`. "preview" et "edit" sont de
nouvelles capacités, sans impact sur l'existant tant que rien ne les appelle
en dehors du nouveau flux d'edit ciblé (voir `image_quality_control.py`).
"""
import os
from dataclasses import dataclass

_DEFAULT_MODEL = "gpt-image-1-mini"
_DEFAULT_QUALITY = "medium"
_VALID_QUALITIES = {"low", "medium", "high", "auto"}
_VALID_PURPOSES = {"preview", "final", "edit"}


def _legacy_model() -> str:
    return os.environ.get("OPENAI_IMAGE_MODEL", "").strip() or _DEFAULT_MODEL


def _legacy_quality() -> str:
    q = os.environ.get("OPENAI_IMAGE_QUALITY", "").strip().lower()
    return q if q in _VALID_QUALITIES else _DEFAULT_QUALITY


def _env_model(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _env_quality(name: str, default: str) -> str:
    q = os.environ.get(name, "").strip().lower()
    return q if q in _VALID_QUALITIES else default


@dataclass(frozen=True)
class ModelSelection:
    model: str
    quality: str
    purpose: str


def select_model(purpose: str) -> ModelSelection:
    """`purpose` : "preview" (itération rapide, pas encore branché sur le
    worker — capacité disponible pour un futur appelant), "final" (image de
    production, chemin utilisé aujourd'hui par le pipeline), "edit"
    (correction ciblée d'une image existante via /v1/images/edits)."""
    if purpose not in _VALID_PURPOSES:
        raise ValueError(f"purpose inconnu : {purpose!r} (attendu {_VALID_PURPOSES})")

    if purpose == "preview":
        model = _env_model("IMAGE_MODEL_FAST", _legacy_model())
        quality = _env_quality("IMAGE_PREVIEW_QUALITY", "low")
    elif purpose == "edit":
        # gpt-image-1 = seul modèle supportant input_fidelity=high (déjà le
        # cas dans openai_images.py pour l'ancrage historique) — la fidélité
        # à l'image de départ est justement ce qu'on veut pour une correction
        # ciblée, contrairement à la génération "final" par scène.
        model = _env_model("IMAGE_MODEL_EDIT", "gpt-image-1")
        quality = _env_quality("IMAGE_EDIT_QUALITY", "high")
    else:  # "final"
        model = _env_model("IMAGE_MODEL_PREMIUM", _legacy_model())
        quality = _env_quality("IMAGE_FINAL_QUALITY", _legacy_quality())

    return ModelSelection(model=model, quality=quality, purpose=purpose)


# $/image, approximatif — mêmes chiffres que documentés historiquement dans
# openai_images.py (mesurés en usage réel : mini/medium ≈ 0,03 $, mini/high ≈
# 0,06 $) ; gpt-image-1 extrapolé (~x3-4 le coût de -mini, même doc). Sert
# uniquement au reporting (`image_generation_report`), jamais à une décision
# bloquante.
_COST_TABLE = {
    ("gpt-image-1-mini", "low"): 0.015,
    ("gpt-image-1-mini", "medium"): 0.03,
    ("gpt-image-1-mini", "high"): 0.06,
    ("gpt-image-1", "low"): 0.05,
    ("gpt-image-1", "medium"): 0.10,
    ("gpt-image-1", "high"): 0.19,
}


def estimate_cost(model: str, quality: str) -> float:
    """Coût estimé en $ pour une image, ou 0.0 si modèle/qualité inconnus du
    tableau (ex. modèle futur pas encore documenté ici) — jamais bloquant."""
    return _COST_TABLE.get((model, quality), 0.0)
