"""Générateurs déterministes de l'Explainer : un sujet STRUCTURÉ (des paramètres) -> narration + storyboard + composition de
gabarits, sans aucun modèle de langage. Chaque générateur renvoie un `spec` :

    {"topic", "lines", "storyboard", "composition": {"plans": [{id, template, params, guide}]}}

que `pipeline.generate(spec=...)` consomme à la place du réalisateur et du compositeur. Seule la voix reste externe (ElevenLabs).
"""
from __future__ import annotations

from . import compound_interest

REGISTRY = {"compound_interest": compound_interest}


def build(name: str, params: dict, lang: str = "fr") -> dict:
    if name not in REGISTRY:
        raise ValueError(f"générateur inconnu : {name!r} (disponibles : {sorted(REGISTRY)})")
    return REGISTRY[name].build(params, lang)
