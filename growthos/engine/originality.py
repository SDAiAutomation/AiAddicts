"""Diagnostic d'originalité / anti-répétition — capacité NOUVELLE et OPT-IN
(`ORIGINALITY_CHECK_ENABLED=false` par défaut, voir `.env.example`). Compare
le script d'une nouvelle vidéo aux ~20 dernières vidéos du même compte
(concept, personnage, situation, environnement, hook, progression, twist,
conclusion, vocabulaire, composition visuelle) et signale les ressemblances
fortes — priorité n°1 de PRODUCT_DOCTRINE.md (section « Originalité et
anti-répétition »).

Jamais bloquant, même philosophie best-effort que `image_quality_control.py` :
capacité désactivée, modèle non configuré, échec réseau ou réponse malformée
-> `None`. L'appelant (`engine/assembler.py`) traite `None` comme "diagnostic
indisponible", jamais une erreur qui ferait échouer la génération.

`overall_similarity` est un score diagnostique heuristique, jamais une
certification de doublon ni de l'éligibilité à la monétisation d'une
plateforme. Sans historique (compte neuf), `history_available=False` — c'est
un signal distinct de "0% de ressemblance", jamais confondu avec lui.

Limites connues de cette V1 (voir PRODUCT_DOCTRINE.md, critères d'acceptation
« Anti-répétition ») :
- Seuils par défaut non calibrés sur un corpus annoté (aucun corpus de ce type
  n'existe encore dans ce repo) — à ajuster une fois des exemples réels notés.
- Pas de "reprise plafonnée" au sens strict : ce repo ne génère pas de script
  (voir `engine/script.py`), il ne peut donc pas réécrire puis revérifier —
  seulement signaler une fois pour revue humaine/frontend.
- La dimension "composition visuelle" est approximée via le texte des champs
  `visual` de chaque bloc, pas une comparaison d'images réellement rendues
  (pas de pgvector/embeddings dans ce repo).
"""
import dataclasses
import json
import os
from dataclasses import dataclass, field

import requests

CHAT_URL = "https://api.openai.com/v1/chat/completions"

_DEFAULT_HISTORY_LIMIT = 20
_DEFAULT_THRESHOLD_FLAG = 75
_MAX_BLOCK_CHARS = 600

_INSTRUCTIONS = (
    "Tu es un contrôle d'originalité pour des vidéos courtes générées par IA. "
    "Compare `newScript` aux vidéos de `pastScripts` (même compte) sur : concept, "
    "personnage, situation, environnement, accroche (hook), progression, "
    "retournement, conclusion, vocabulaire et composition visuelle (déduite des "
    "champs `visual`). Un personnage récurrent seul, ou une accroche/formule "
    "partagée, n'est PAS en soi un doublon : seul un chevauchement substantiel du "
    "concept complet compte. Un simple changement de noms ne suffit pas à rendre "
    "deux histoires différentes si le reste est identique.\n\n"
    "Réponds UNIQUEMENT en JSON, exactement cette forme : "
    '{"overallSimilarity": <0-100 ou absent>, "dimensions": [{"name": <string>, '
    '"similarity": <0-100>, "matchedVideoIds": [<string>], "explanation": <string>}], '
    '"suggestion": <string ou null>}. `dimensions` : une entrée par axe comparé qui '
    "présente une ressemblance notable (liste vide si rien de proche). `suggestion` "
    ": une proposition concrète et substantiellement différente si la ressemblance "
    "est forte, sinon null."
)


@dataclass(frozen=True)
class OriginalityResult:
    too_similar: bool
    overall_similarity: int  # 0-100, diagnostic heuristique — jamais une certification
    compared_count: int
    history_available: bool  # False seulement si aucune vidéo comparée (distinct de 0%)
    dimensions: list = field(default_factory=list)
    matched_video_ids: list = field(default_factory=list)
    suggestion: str | None = None
    model: str = ""
    usage: dict | None = None  # {"input": tokens, "output": tokens} — pour le coût


def originality_enabled() -> bool:
    return os.environ.get("ORIGINALITY_CHECK_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _clamp_score(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, n))


def _reduce_script(script: dict) -> dict:
    """Ne garde que les champs pertinents pour la comparaison (pas
    `hashtags`/`caption_style`/etc.), tronqués pour borner le coût d'un appel
    avec jusqu'à `ORIGINALITY_HISTORY_LIMIT` scripts passés."""
    blocks = script.get("blocks") or []
    characters = script.get("characters") or []
    return {
        "title": script.get("title"),
        "contentGoal": script.get("content_goal"),
        "niche": script.get("niche"),
        "characters": [
            {"name": c.get("name"), "description": c.get("description")}
            for c in characters if isinstance(c, dict)
        ],
        "blocks": [
            {
                "role": b.get("role"),
                "text": str(b.get("text") or "")[:_MAX_BLOCK_CHARS],
                "visual": str(b.get("visual") or "")[:_MAX_BLOCK_CHARS],
            }
            for b in blocks if isinstance(b, dict)
        ],
    }


def _build_messages(script: dict, history: list[dict]) -> list[dict]:
    new_reduced = _reduce_script(script)
    past = []
    for row in history:
        reduced = _reduce_script(row.get("script") or {})
        reduced["id"] = row.get("id")
        reduced["createdAt"] = row.get("created_at")
        past.append(reduced)
    user_content = json.dumps({"newScript": new_reduced, "pastScripts": past}, ensure_ascii=False)
    return [
        {"role": "system", "content": _INSTRUCTIONS},
        {"role": "user", "content": user_content},
    ]


def parse_originality_response(raw: dict, compared_count: int, history_available: bool) -> "OriginalityResult | None":
    """Valide à la main le JSON retourné par le modèle (pas de `pydantic` —
    convention du repo, voir `engine/image_quality_control.py`). `None` si la
    forme est inexploitable : traité comme un diagnostic indisponible par
    l'appelant, jamais une exception."""
    if not isinstance(raw, dict):
        return None
    dims_raw = raw.get("dimensions")
    if not isinstance(dims_raw, list):
        return None

    dimensions: list[dict] = []
    matched: set[str] = set()
    for d in dims_raw:
        if not isinstance(d, dict):
            continue
        similarity = _clamp_score(d.get("similarity"))
        if similarity is None:
            continue
        ids_raw = d.get("matchedVideoIds")
        ids = [str(i) for i in ids_raw] if isinstance(ids_raw, list) else []
        matched.update(ids)
        dimensions.append({
            "name": str(d.get("name") or "?"),
            "similarity": similarity,
            "matchedVideoIds": ids,
            "explanation": str(d.get("explanation") or ""),
        })

    overall = _clamp_score(raw.get("overallSimilarity"))
    if overall is None:
        overall = max((d["similarity"] for d in dimensions), default=0)

    threshold = _int_env("ORIGINALITY_THRESHOLD_FLAG", _DEFAULT_THRESHOLD_FLAG)
    suggestion_raw = raw.get("suggestion")
    suggestion = str(suggestion_raw) if suggestion_raw else None

    return OriginalityResult(
        too_similar=overall >= threshold,
        overall_similarity=overall,
        compared_count=compared_count,
        history_available=history_available,
        dimensions=dimensions,
        matched_video_ids=sorted(matched),
        suggestion=suggestion,
    )


def check_originality(script: dict, history: list[dict]) -> "OriginalityResult | None":
    """`None` si le check est désactivé (`ORIGINALITY_CHECK_ENABLED`), le
    modèle n'est pas configuré (`ORIGINALITY_MODEL`), ou tout échec
    réseau/parsing — jamais d'exception. Sans historique, retourne un
    résultat `history_available=False` sans appel réseau (aucun coût) :
    conforme à la doctrine, "sans historique, signaler que la comparaison est
    indisponible" plutôt que déclarer 0% de ressemblance."""
    if not originality_enabled():
        return None
    if not history:
        return OriginalityResult(
            too_similar=False,
            overall_similarity=0,
            compared_count=0,
            history_available=False,
        )

    model = os.environ.get("ORIGINALITY_MODEL", "").strip()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not model or not api_key:
        return None

    limit = max(1, _int_env("ORIGINALITY_HISTORY_LIMIT", _DEFAULT_HISTORY_LIMIT))
    bounded_history = history[:limit]

    try:
        resp = requests.post(
            CHAT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": _build_messages(script, bounded_history),
            },
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        result = parse_originality_response(json.loads(content), len(bounded_history), True)
        if result is None:
            return None
        usage_raw = body.get("usage") or {}
        usage = {
            "input": int(usage_raw.get("prompt_tokens") or 0),
            "output": int(usage_raw.get("completion_tokens") or 0),
        }
        return dataclasses.replace(result, model=model, usage=usage)
    except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
        print(f"       originalité : échec ({exc}) — diagnostic indisponible")
        return None
