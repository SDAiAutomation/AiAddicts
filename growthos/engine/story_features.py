"""Classification d'une vidéo pour la mémoire éditoriale (`engine/learning.py`) :
archétype narratif (liste de PRODUCT_DOCTRINE.md) et type d'accroche.

Calculée une seule fois par vidéo puis mise en cache dans
`content_items.story_features` (voir `refresh_learning.py`). Best-effort,
même philosophie que `engine/originality.py` : modèle non configuré
(`LEARNING_MODEL`, pas de défaut codé en dur), échec réseau ou réponse
malformée -> `None`, jamais d'exception. Une vidéo non classée est
simplement absente des regroupements concernés.
"""
import json
import os
import time

import requests

CHAT_URL = "https://api.openai.com/v1/chat/completions"
# 2 : "mystère/révélation" réservé aux histoires sans ressort plus précis
# (en v1 il absorbait presque tout : chaque histoire a une révélation finale).
VERSION = 2
_RATE_LIMIT_RETRIES = 3

ARCHETYPES = (
    "mystère/révélation",
    "loyauté inattendue",
    "découverte impossible",
    "transformation",
    "course contre la montre",
    "animal incompris",
    "mystère historique",
    "relation humain–animal",
    "identité cachée",
    "intelligence inattendue",
    "survie",
    "réaction en chaîne",
    "question non résolue",
    "comédie",
    "aventure",
    "amitié inter-espèces",
    "autre",
)

HOOK_TYPES = (
    "question",
    "liste chiffrée",
    "avertissement",
    "énigme",
    "mise en situation",
    "affirmation choc",
    "autre",
)

QUIZ_ARCHETYPE = "quiz"

_MAX_TEXT_CHARS = 2500

_INSTRUCTIONS = (
    "Tu classes une vidéo courte pour l'analyse de performance d'une chaîne. "
    "Choisis l'archétype narratif DOMINANT : le ressort émotionnel qui fait "
    "tenir l'histoire (pas son décor, ni l'espèce de l'animal). Presque toutes "
    "ces histoires se terminent par une révélation : ce n'est PAS un critère. "
    "Choisis d'abord l'archétype le plus spécifique qui s'applique (ex. un "
    "animal qui revient chaque jour vers quelqu'un = loyauté inattendue ou "
    "relation humain–animal ; un animal qui fait quelque chose d'étonnamment "
    "malin = intelligence inattendue) ; « mystère/révélation » seulement si "
    "l'énigme elle-même est le seul ressort. Classe aussi la première phrase "
    "(l'accroche). Réponds UNIQUEMENT en JSON : "
    '{"archetype": <une valeur de archetypes>, "hookType": <une valeur de hookTypes>}.'
)


def _script_text(script: dict) -> str:
    blocks = script.get("blocks") or []
    text = " ".join(str(b.get("text") or "") for b in blocks if isinstance(b, dict))
    return text[:_MAX_TEXT_CHARS]


def _hook(script: dict) -> str:
    return next(
        (str(b.get("text") or "").strip() for b in (script.get("blocks") or [])
         if isinstance(b, dict) and b.get("role") == "hook"),
        "",
    )


def parse_response(raw) -> dict | None:
    """Valide la réponse du modèle ; toute valeur hors liste -> "autre"."""
    if not isinstance(raw, dict):
        return None
    archetype = str(raw.get("archetype") or "").strip().lower()
    hook_type = str(raw.get("hookType") or "").strip().lower()
    if not archetype and not hook_type:
        return None
    return {
        "archetype": archetype if archetype in ARCHETYPES else "autre",
        "hookType": hook_type if hook_type in HOOK_TYPES else "autre",
    }


def classify(title: str, script: dict) -> dict | None:
    """`{"archetype", "hookType", "model", "version"}` ou `None`. Un quiz n'a
    pas d'archétype narratif : classé "quiz" sans appel réseau."""
    if str(script.get("content_format") or "") == "quiz" or script.get("quiz"):
        return {"archetype": QUIZ_ARCHETYPE, "hookType": "question", "model": "", "version": VERSION}

    model = os.environ.get("LEARNING_MODEL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not model or not api_key:
        return None

    payload = {
        "archetypes": list(ARCHETYPES),
        "hookTypes": list(HOOK_TYPES),
        "title": title,
        "hook": _hook(script),
        "script": _script_text(script),
    }
    try:
        for attempt in range(_RATE_LIMIT_RETRIES + 1):
            resp = requests.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _INSTRUCTIONS},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
                timeout=60,
            )
            # 429 = limite de débit (on patiente) ou crédit épuisé
            # (insufficient_quota : inutile d'insister).
            if resp.status_code != 429 or "insufficient_quota" in resp.text or attempt == _RATE_LIMIT_RETRIES:
                break
            time.sleep(5 * (attempt + 1))
        if resp.status_code == 429:
            code = (resp.json().get("error") or {}).get("code")
            print(f"       classification : refusée par OpenAI (429 {code})")
            return None
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = parse_response(json.loads(content))
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
        print(f"       classification : échec ({exc})")
        return None
    if parsed is None:
        return None
    return {**parsed, "model": model, "version": VERSION}
