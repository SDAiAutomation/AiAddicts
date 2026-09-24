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

Deux seuils (recalibrés le 2026-09-24 sur 9 vidéos réelles de 2 comptes +
1 clone : ressemblance organique 62-85, clone 100 — les séries reprennent
volontairement un gabarit, qui ne doit pas bloquer) :
- `ORIGINALITY_THRESHOLD_BLOCK` (90) : `too_similar`, bascule en revue ;
- `ORIGINALITY_THRESHOLD_WARN` (70) : `warn`, simple avertissement, le statut
  ne change pas.

Limites connues de cette V1 (voir PRODUCT_DOCTRINE.md, critères d'acceptation
« Anti-répétition ») :
- Seuils calibrés sur un échantillon minuscule, pas sur un corpus annoté
  (aucun n'existe encore dans ce repo) — à revoir une fois des paires réelles
  notées.
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
_DEFAULT_THRESHOLD_BLOCK = 90
_DEFAULT_THRESHOLD_WARN = 70
_VISUAL_DIMENSION_KEYWORDS = ("visu", "composition", "image")
_MAX_BLOCK_CHARS = 600

_INSTRUCTIONS = (
    "Tu es un contrôle d'originalité pour des vidéos courtes générées par IA. "
    "Compare `newScript` aux vidéos de `pastScripts` (même compte) sur : concept, "
    "personnage, situation, environnement, accroche (hook), progression, "
    "retournement, conclusion, vocabulaire et composition visuelle (déduite des "
    "champs `visual` ; si ces champs sont vides d'un côté ou de l'autre, NE note "
    "PAS la composition visuelle et ne la devine pas depuis le texte). Un "
    "gabarit de série partagé (même format d'accroche, même structure, même "
    "univers) est attendu et ne justifie pas à lui seul un score élevé. Un personnage récurrent seul, ou une accroche/formule "
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
    too_similar: bool  # >= seuil de blocage : bascule en revue
    overall_similarity: int  # 0-100, diagnostic heuristique — jamais une certification
    compared_count: int
    history_available: bool  # False seulement si aucune vidéo comparée (distinct de 0%)
    dimensions: list = field(default_factory=list)
    matched_video_ids: list = field(default_factory=list)
    suggestion: str | None = None
    model: str = ""
    usage: dict | None = None  # {"input": tokens, "output": tokens} — pour le coût
    warn: bool = False  # >= seuil d'avertissement (ou bloquant) : signalé, sans bloquer


def originality_enabled() -> bool:
    return os.environ.get("ORIGINALITY_CHECK_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def thresholds() -> tuple[int, int]:
    """(avertissement, blocage). `ORIGINALITY_THRESHOLD_FLAG` (ancien nom,
    seuil unique) reste lu comme seuil de blocage si le nouveau est absent.
    L'avertissement ne dépasse jamais le blocage."""
    block = _int_env(
        "ORIGINALITY_THRESHOLD_BLOCK",
        _int_env("ORIGINALITY_THRESHOLD_FLAG", _DEFAULT_THRESHOLD_BLOCK),
    )
    warn = min(_int_env("ORIGINALITY_THRESHOLD_WARN", _DEFAULT_THRESHOLD_WARN), block)
    return warn, block


def _has_visuals(script: dict) -> bool:
    return any(
        isinstance(b, dict) and str(b.get("visual") or "").strip()
        for b in (script.get("blocks") or [])
    )


def _is_visual_dimension(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered for k in _VISUAL_DIMENSION_KEYWORDS)


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


def parse_originality_response(
    raw: dict, compared_count: int, history_available: bool, visuals_available: bool = True,
) -> "OriginalityResult | None":
    """Valide à la main le JSON retourné par le modèle (pas de `pydantic` —
    convention du repo, voir `engine/image_quality_control.py`). `None` si la
    forme est inexploitable : traité comme un diagnostic indisponible par
    l'appelant, jamais une exception. Sans champs `visual` à comparer
    (`visuals_available=False`), une dimension visuelle notée quand même est
    écartée : le modèle l'invente depuis le texte (constaté le 2026-09-23)."""
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
        if not visuals_available and _is_visual_dimension(str(d.get("name") or "")):
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

    warn_threshold, block_threshold = thresholds()
    suggestion_raw = raw.get("suggestion")
    suggestion = str(suggestion_raw) if suggestion_raw else None

    return OriginalityResult(
        too_similar=overall >= block_threshold,
        warn=overall >= warn_threshold,
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
            # 60 s a expiré 1 fois sur 10 au premier essai réel (20 scripts
            # passés en entrée, modèle à raisonnement).
            timeout=120,
        )
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        visuals_available = _has_visuals(script) and any(
            _has_visuals(row.get("script") or {}) for row in bounded_history
        )
        result = parse_originality_response(
            json.loads(content), len(bounded_history), True, visuals_available=visuals_available,
        )
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
