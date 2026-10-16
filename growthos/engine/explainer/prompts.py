"""Registre versionné des prompts de l'Explainer (doctrine : chaque génération référence les versions exactes)."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
VERSIONS = {"explainer-script": "v1", "explainer-director": "v1", "explainer-animator": "v1", "runtime-api": "0.1.0"}


def load(name: str) -> str:
    """Texte d'un prompt. `animator` = consignes + API du runtime (fichier partagé avec l'animateur)."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text


def versions() -> dict[str, str]:
    return dict(VERSIONS)
