"""Registre versionné des prompts de l'Explainer (doctrine : chaque génération référence les versions exactes)."""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
VERSIONS = {"explainer-script": "v1", "explainer-director": "v1", "explainer-animator": "v1", "explainer-composer": "v1", "runtime-api": "0.1.0"}


def load(name: str) -> str:
    """Texte d'un prompt. `animator` = consignes + API du runtime (fichier partagé avec l'animateur)."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text


LANGUAGE_NAMES = {"fr": "français", "en": "English", "es": "español", "de": "Deutsch", "it": "italiano", "pt": "português"}


def language_note(language: str | None) -> str:
    """Consigne de langue ajoutée au BRIEF utilisateur (pas au prompt système, qui reste statique pour le cache).

    Les consignes et les exemples de l'Explainer sont en français (« Salut ! », Awa, Léa) : sans cette note, un modèle
    peut recopier ces exemples dans une vidéo dont la narration est dans une autre langue."""
    code = (language or "fr").strip().lower()
    name = LANGUAGE_NAMES.get(code, code)
    return (f"LANGUE DE LA VIDÉO : {name} ({code}). La narration est dans cette langue : TOUS les textes affichés (titres, étiquettes, "
            f"éléments de liste, légendes, mots-clés, bulles du guide, messages et noms de contact du téléphone) sont écrits dans cette langue. "
            f"Les exemples en français des consignes (« Salut ! », Awa, Léa, « On mange ce soir ? ») illustrent seulement le format : ne les recopie jamais.")


def versions() -> dict[str, str]:
    return dict(VERSIONS)
