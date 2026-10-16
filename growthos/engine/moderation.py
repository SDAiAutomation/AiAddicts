"""Modération du script avant toute dépense (OpenAI omni-moderation, gratuite).

Appelée dans `assembler.run_for_content_item` après la validation du script et AVANT la réservation du crédit :
un contenu refusé ne coûte ni crédit ni appel payant. Le script étant construit par le front à partir du sujet de
l'utilisateur, il contient déjà tout le texte qui sera dit et affiché.

On ne bloque que les catégories graves ; `violence`, `harassment`, `illicit` et `self-harm` seuls sont exclus
exprès (récits sombres, faits divers, prévention : trop de faux positifs). Échec du service = on laisse passer
(disponibilité) sauf si MODERATION_FAIL_CLOSED=1. Désactivable : MODERATION_ENABLED=0.
"""
import os

import requests

URL = "https://api.openai.com/v1/moderations"
MODEL = "omni-moderation-latest"
BLOCKED = {
    "sexual", "sexual/minors", "hate", "hate/threatening", "harassment/threatening",
    "self-harm/intent", "self-harm/instructions", "illicit/violent", "violence/graphic",
}
CHUNK = 4000  # caractères par entrée envoyée
MAX_CHARS = 60000  # un script normal en fait < 5000 ; au-delà on tronque plutôt que de payer du temps


class ModerationError(RuntimeError):
    pass


def enabled() -> bool:
    return os.environ.get("MODERATION_ENABLED", "1") != "0"


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node] if node.strip() else []
    if isinstance(node, dict):
        return [s for v in node.values() for s in _strings(v)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in _strings(v)]
    return []


def _chunks(texts: list[str]) -> list[str]:
    joined = "\n".join(texts)[:MAX_CHARS]
    return [joined[i:i + CHUNK] for i in range(0, len(joined), CHUNK)]


def blocked_categories(script: dict) -> set[str]:
    """Catégories graves détectées dans tout le texte du script ; vide si propre ou service indisponible."""
    inputs = _chunks(_strings(script))
    key = os.environ.get("OPENAI_API_KEY")
    if not inputs:
        return set()
    try:
        if not key:
            raise RuntimeError("OPENAI_API_KEY absente")
        resp = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, json={"model": MODEL, "input": inputs}, timeout=30)
        resp.raise_for_status()
        results = resp.json()["results"]
    except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
        if os.environ.get("MODERATION_FAIL_CLOSED") == "1":
            raise ModerationError("vérification de contenu indisponible, réessaie plus tard") from exc
        print(f"       (modération indisponible, génération non bloquée : {exc})")
        return set()
    return {c for r in results for c, hit in r.get("categories", {}).items() if hit and c in BLOCKED}


def check_script(script: dict) -> None:
    """Lève ModerationError si le script relève d'une catégorie interdite."""
    if not enabled():
        return
    hit = blocked_categories(script)
    if hit:
        raise ModerationError(
            "Contenu refusé : ce sujet relève d'une catégorie interdite par les règles d'usage de Faceloop "
            f"({', '.join(sorted(hit))}). Aucun crédit n'a été débité."
        )
