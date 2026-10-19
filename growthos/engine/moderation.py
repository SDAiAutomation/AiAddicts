"""Modération du script avant toute dépense (OpenAI omni-moderation, gratuite).

Appelée dans `assembler.run_for_content_item` après la validation du script et AVANT la réservation du crédit :
un contenu refusé ne coûte ni crédit ni appel payant. Le script étant construit par le front à partir du sujet de
l'utilisateur, il contient déjà tout le texte qui sera dit et affiché.

On ne bloque que les catégories graves ; `violence`, `harassment`, `illicit` et `self-harm` seuls sont exclus
exprès (récits sombres, faits divers, prévention : trop de faux positifs). Échec du service = on laisse passer
(disponibilité) sauf si MODERATION_FAIL_CLOSED=1. Désactivable : MODERATION_ENABLED=0.

Seconde couche (Claude Haiku) : la modération OpenAI ne voit pas la fraude (`illicit` est exclue exprès). Or le
fournisseur de voix interdit de générer du contenu frauduleux, prédateur ou abusif (avertissement reçu le
2026-10-19). Un court appel classe le script : arnaque réellement facilitée, usurpation, faux avis, manipulation
d'une personne vulnérable, harcèlement. Les contenus qui EXPLIQUENT une arnaque pour s'en protéger restent permis.
C'est un garde-fou, pas une garantie de conformité. Désactivable : FRAUD_CHECK_ENABLED=0 ; modèle : FRAUD_CHECK_MODEL.
"""
import json
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


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
FRAUD_MODEL = "claude-haiku-5-5"
FRAUD_SYSTEM = (
    "Tu es un contrôleur de conformité pour un générateur de vidéos courtes avec voix de synthèse. "
    "Tu reçois le texte d'un script. Réponds UNIQUEMENT par un objet JSON : "
    '{"blocked": bool, "category": "fraud|impersonation|fake_reviews|predatory|harassment|none", "reason": "une phrase"}.\n'
    "Bloque (blocked=true) seulement si le texte aide réellement à commettre l'abus ou le commet : mode d'emploi pour "
    "escroquer ou arnaquer, phishing, fausse identité ou usurpation d'une personne réelle, faux témoignages ou faux avis "
    "présentés comme vrais, promesses de gains garantis pour piéger, manipulation ou exploitation de personnes "
    "vulnérables, harcèlement ciblé.\n"
    "NE bloque PAS : le contenu éducatif ou de prévention qui explique comment fonctionne une arnaque pour s'en "
    "protéger, l'histoire, le journalisme, la fiction clairement fictive, les quiz et les faits. En cas de doute "
    "raisonnable, blocked=false."
)


def fraud_verdict(script: dict) -> dict | None:
    """Verdict Claude {'blocked', 'category', 'reason'}, ou None si le service est indisponible (sauf mode fermé)."""
    if os.environ.get("FRAUD_CHECK_ENABLED", "1") == "0":
        return None
    text = "\n".join(_strings(script))[:MAX_CHARS]
    if not text:
        return None
    try:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY absente")
        resp = requests.post(
            ANTHROPIC_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"model": os.environ.get("FRAUD_CHECK_MODEL", FRAUD_MODEL), "max_tokens": 200, "system": FRAUD_SYSTEM,
                  "messages": [{"role": "user", "content": text}]},
            timeout=30,
        )
        resp.raise_for_status()
        raw = "".join(b.get("text", "") for b in resp.json()["content"] if b.get("type") == "text")
        verdict = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        verdict["blocked"] = verdict["blocked"] is True   # seule une valeur booléenne vraie bloque
        return verdict
    except (requests.RequestException, KeyError, ValueError, RuntimeError) as exc:
        if os.environ.get("MODERATION_FAIL_CLOSED") == "1":
            raise ModerationError("vérification de contenu indisponible, réessaie plus tard") from exc
        print(f"       (contrôle fraude indisponible, génération non bloquée : {type(exc).__name__}: {exc})")
        return None


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
    verdict = fraud_verdict(script)
    if verdict and verdict["blocked"]:
        raise ModerationError(
            "Contenu refusé : ce sujet semble faciliter une fraude, une usurpation ou un abus, interdits par les règles "
            f"d'usage de Faceloop et de nos fournisseurs ({verdict.get('category', 'n/d')}). Reformule le sujet de façon "
            "éducative (comment reconnaître et éviter) ou contacte-nous si c'est une erreur. Aucun crédit n'a été débité."
        )


def check_integrity(script: dict) -> None:
    """Contrôles déterministes bloquants (calcul faux, projection sans hypothèse, promesse de CTA, « garanti »,
    texte de remplissage) AVANT la voix et le crédit. Avant, ils ne tournaient qu'après la synthèse vocale : le texte
    était déjà parti chez le fournisseur de voix. Désactivable : INTEGRITY_PRECHECK=0. Une panne du contrôle
    lui-même ne bloque pas la génération (le contrôle qualité d'après-rendu reste en place)."""
    if os.environ.get("INTEGRITY_PRECHECK", "1") == "0":
        return
    from . import retention   # import tardif : retention importe integrity, pas l'inverse
    try:
        issues = retention.blocking_integrity_issues(script)
    except Exception as exc:  # noqa: BLE001
        print(f"       (contrôle d'intégrité avant voix indisponible, génération non bloquée : {type(exc).__name__}: {exc})")
        return
    if issues:
        details = " ; ".join(i["message"] for i in issues[:4])
        raise ModerationError(
            f"Script à corriger avant génération : {details} Aucun crédit n'a été débité et rien n'a été envoyé au service de voix."
        )
