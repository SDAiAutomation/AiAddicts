"""Sélection du modèle/qualité OpenAI Images par usage (preview/final/edit) +
estimation de coût. Voir `engine/openai_images.py` pour l'appel API réel et
`engine/visuals.py` pour l'orchestration qui appelle `select_model`.

Le mode final utilise `OPENAI_IMAGE_MODEL`/`OPENAI_IMAGE_QUALITY` lorsqu'ils
sont renseignés et GPT Image 2.5 Flare en qualité medium sinon. Les variables
par usage permettent de surcharger preview/final/edit séparément.
"""
import os
from dataclasses import dataclass

_DEFAULT_MODEL = "gpt-image-2.5-flare"
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
        # GPT Image 2.5 conserve déjà une haute fidélité des images d'entrée ;
        # openai_images n'envoie l'ancien paramètre input_fidelity que si une
        # configuration force explicitement gpt-image-1.
        model = _env_model("IMAGE_MODEL_EDIT", "gpt-image-2.5-flare")
        quality = _env_quality("IMAGE_EDIT_QUALITY", "high")
    else:  # "final"
        model = _env_model("IMAGE_MODEL_PREMIUM", _legacy_model())
        quality = _env_quality("IMAGE_FINAL_QUALITY", _legacy_quality())

    return ModelSelection(model=model, quality=quality, purpose=purpose)


# $/image, approximatif — chiffres des anciens modèles seulement. GPT Image
# 2.5 est facturé en tokens et reste à 0 ici plutôt que d'afficher un faux
# montant fixe. Sert uniquement au reporting, jamais à une décision bloquante.
# Les chiffres historiques ci-dessous ne servent qu'aux configurations qui
# conservent explicitement un ancien modèle.
_COST_TABLE = {
    ("gpt-image-1-mini", "low"): 0.015,
    ("gpt-image-1-mini", "medium"): 0.03,
    ("gpt-image-1-mini", "high"): 0.06,
    ("gpt-image-1", "low"): 0.05,
    ("gpt-image-1", "medium"): 0.10,
    ("gpt-image-1", "high"): 0.19,
}


def _price_per_million(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def cost_from_usage(usage: dict | None) -> float | None:
    """Coût en $ à partir des tokens réellement facturés par l'API. Les tarifs
    ($ par million de tokens) viennent de l'environnement — volontairement
    pas codés en dur, ils changent et diffèrent selon le modèle :
      IMAGE_PRICE_TEXT_IN_PER_M, IMAGE_PRICE_IMAGE_IN_PER_M, IMAGE_PRICE_IMAGE_OUT_PER_M
    None si l'usage ou le tarif de sortie manque (on retombe alors sur le
    tableau). Un tarif d'entrée absent compte pour 0 : la sortie image
    domine le coût."""
    if not usage:
        return None
    out_price = _price_per_million("IMAGE_PRICE_IMAGE_OUT_PER_M")
    if out_price is None:
        return None
    text_in = _price_per_million("IMAGE_PRICE_TEXT_IN_PER_M") or 0.0
    image_in = _price_per_million("IMAGE_PRICE_IMAGE_IN_PER_M") or 0.0
    return (
        usage.get("input_text", 0) * text_in
        + usage.get("input_image", 0) * image_in
        + usage.get("output", 0) * out_price
    ) / 1_000_000


def estimate_cost(model: str, quality: str, usage: dict | None = None) -> float:
    """Coût estimé en $ pour une image. Préfère le calcul sur les tokens
    réels (`usage` + tarifs d'environnement) ; sinon le tableau historique ;
    0.0 si modèle/qualité inconnus (ex. modèle facturé au token sans tarifs
    configurés) — jamais bloquant. Les tokens restent dans le rapport, le
    coût peut donc être recalculé après coup."""
    from_usage = cost_from_usage(usage)
    if from_usage is not None:
        return from_usage
    return _COST_TABLE.get((model, quality), 0.0)
