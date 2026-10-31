"""Instantané sémantique en LECTURE SEULE d'un script (Standard, Story dialogué, Story Visual) + son empreinte.

Aucun adaptateur ne modifie le script reçu (testé par comparaison profonde). Le texte évalué est le texte FINAL tel qu'il
est fourni : si un nettoyage retire une scène, l'appelant reconstruit l'instantané et l'ancienne revue devient `stale`.
"""
from __future__ import annotations

import hashlib
import json

from . import contract as c

_SOURCE_KEYS = ("source_id", "url", "title", "accessed_at", "content_kind", "content", "locator", "allowed_claims",
                "limitations", "verification")
_TIMING_SOURCES = ("measured", "estimated", "unknown")


def canonical_json(value) -> str:
    """Sérialisation canonique déterministe (clés triées, sans espaces, Unicode non échappé).

    shortcut: pas de nombres flottants (refusés) et tri par point de code, pas par unité UTF-16 comme RFC 8785 ; identique pour
    nos clés ASCII fixes. À remplacer par une vraie JCS partagée avec le miroir TypeScript avant toute intégration production.
    """
    def check(v):
        if isinstance(v, float):
            raise c.ReviewError(c.INVALID_RESPONSE, "floats are not allowed in a hashed snapshot")
        if isinstance(v, dict):
            for k, x in v.items():
                if not isinstance(k, str):
                    raise c.ReviewError(c.INVALID_RESPONSE, "snapshot keys must be strings")
                check(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                check(x)
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_hash(core: dict) -> str:
    return hashlib.sha256(canonical_json(core).encode("utf-8")).hexdigest()


def _unit(unit_id: str, origin_path: str, channel: str, text, *, native_id=None, speaker_id=None, declared_role=None) -> dict:
    return {"unit_id": unit_id, "origin": {"path": origin_path, "native_id": native_id}, "channel": channel,
            "text": text, "speaker_id": speaker_id, "declared_role": declared_role}


def _clean_source(src: dict) -> dict:
    if not isinstance(src, dict) or not isinstance(src.get("source_id"), str) or not src["source_id"].strip():
        raise c.ReviewError(c.INVALID_RESPONSE, "each source needs a source_id")
    out = {k: src[k] for k in _SOURCE_KEYS if k in src}
    out.setdefault("verification", "unknown")
    if out["verification"] not in c.VERIFICATIONS or out.get("content_kind", "curated_summary") not in c.CONTENT_KINDS:
        raise c.ReviewError(c.INVALID_RESPONSE, f"source {src['source_id']}: unknown verification or content_kind")
    out.setdefault("content_kind", "curated_summary")
    if not isinstance(out.get("content", ""), str):
        raise c.ReviewError(c.INVALID_RESPONSE, f"source {src['source_id']}: content must be text")
    out.setdefault("content", "")
    return out


def build_snapshot(*, source_format: str, units: list[dict], organization_id: str, account_id: str, language: str = "fr",
                   truth_mode: str = "unknown", illustration_mode: str = "none", intent: dict | None = None,
                   sources=(), history: dict | None = None, timing: dict | None = None,
                   required_dimensions=c.PILOT_REQUIRED_DIMENSIONS, coverage_gaps=()) -> dict:
    if source_format not in c.SOURCE_FORMATS:
        raise c.ReviewError(c.UNSUPPORTED_FORMAT, f"unsupported source format {source_format!r}")
    if truth_mode not in c.TRUTH_MODES or illustration_mode not in c.ILLUSTRATION_MODES:
        raise c.ReviewError(c.INVALID_RESPONSE, "unknown truth_mode or illustration_mode")
    if not organization_id or not account_id:
        raise c.ReviewError(c.TENANT_MISMATCH, "organization_id and account_id are required")
    if not 1 <= len(units) <= c.MAX_UNITS:
        raise c.ReviewError(c.INPUT_TOO_LARGE, f"{len(units)} units (allowed 1..{c.MAX_UNITS})")
    ids = [u["unit_id"] for u in units]
    if len(set(ids)) != len(ids):
        raise c.ReviewError(c.INVALID_RESPONSE, "unit_id must be unique in a snapshot")
    for u in units:
        if u["channel"] not in c.CHANNELS or not isinstance(u["text"], str) or not u["text"].strip():
            raise c.ReviewError(c.INVALID_RESPONSE, f"unit {u['unit_id']}: bad channel or empty text")
    if sum(len(u["text"]) for u in units) > c.MAX_TEXT_CHARS:
        raise c.ReviewError(c.INPUT_TOO_LARGE, f"text exceeds {c.MAX_TEXT_CHARS} characters (never truncated)")
    clean_sources = [_clean_source(s) for s in sources]
    if len(clean_sources) > c.MAX_SOURCES or sum(len(s["content"]) for s in clean_sources) > c.MAX_SOURCE_CHARS:
        raise c.ReviewError(c.INPUT_TOO_LARGE, "too many sources or too much source text")
    history = history or {"coverage": "none", "refs": []}
    if len(history.get("refs", [])) > c.MAX_HISTORY:
        raise c.ReviewError(c.INPUT_TOO_LARGE, f"history is limited to {c.MAX_HISTORY} items")
    timing = timing or {"source": "unknown", "durations": {}}
    if timing.get("source") not in _TIMING_SOURCES:
        raise c.ReviewError(c.INVALID_RESPONSE, "timing.source must be measured, estimated or unknown")
    if not set(required_dimensions) <= set(c.DIMENSIONS):
        raise c.ReviewError(c.INVALID_RESPONSE, "unknown required dimension")
    core = {"organization_id": organization_id, "account_id": account_id, "policy_version": c.POLICY_VERSION,
            "language": language, "source_format": source_format, "truth_mode": truth_mode,
            "illustration_mode": illustration_mode, "intent": intent or {}, "units": units, "sources": clean_sources,
            "history": history, "timing": timing, "required_dimensions": list(required_dimensions),
            "coverage_gaps": sorted(set(coverage_gaps))}
    return {"schema_version": c.SCHEMA_VERSION, "snapshot_id": snapshot_hash(core), **core}


# --- Adaptateurs de lecture -------------------------------------------------------------------------------------------

# Champs d'un bloc Standard connus POUR NE PAS PORTER de texte de spectateur (ou lus explicitement ci-dessous). Toute autre clé qui contient
# du texte est un texte affiché potentiel que l'adaptateur ne sait pas lire : il devient une LACUNE DE COUVERTURE (`coverage_gaps`) et la
# décision reste `review`. C'est une liste d'autorisation : un champ nouveau est suspect par défaut, jamais ignoré.
_STANDARD_NON_VIEWER_KEYS = {"role", "text", "visual", "shotType", "visualPurpose", "retentionRole", "informationGain", "voice_id",
                             "speaker_id", "hold_after_seconds", "quiz_phase", "quiz_reveal_beat_seconds", "motion_graphic"}
# Racine d'un script Standard. `title` et `blocks` sont lus explicitement ; `motion_graphic(s)` à la racine est lu comme un overlay. Les autres
# clés listées sont des métadonnées du contrat (`engine/script.py`, assembler) qui ne sont pas du texte affiché dans la vidéo : entrées
# (`source_*`, `transformation_mode`), choix de rendu, identifiants, publication (`hashtags`, `thumbnail_*`), diagnostics. Une clé ABSENTE de
# cette liste (par ex. `description`, `overlay`, `caption`, `subtitle`) qui porte du contenu est une lacune de couverture.
_ROOT_OVERLAY_KEYS = {"motion_graphic", "motion_graphics"}
_ROOT_READ_OR_NON_VIEWER_KEYS = {
    "title", "blocks", "niche", "account", "organization", "platform", "aspect_ratio", "caption_style", "language", "content_goal",
    "content_format", "source_type", "source_text", "transformation_mode", "characters", "voice_id", "visual_style", "visual_style_prompt",
    "motion_graphics_theme", "thumbnail_url", "hashtags", "made_for_kids", "contentStrategy", "openLoops", "generationMetadata",
    "retentionDiagnostics", "script_usage"}
# Dans `motion_graphic`, ces clés ne sont pas du texte affiché (type de scène, icône, thème, ancres de narration, champs internes `_*`).
_OVERLAY_SKIP_KEYS = {"sceneType", "type", "icon", "theme", "rhythm", "spoken", "sidesSpoken", "resultSpoken", "verifySpoken"}
_OVERLAY_NUMBER_KEYS = {"value"}  # un nombre sous `value` est affiché (chiffre clé, étape) : il devient une unité on_screen
# Nombres dont le contrat de rendu (`motion_graphics/display_text.py`, `_NUMBER_FIELDS`) fait des paramètres de tracé, pas du texte. Tout autre
# nombre d'un motion_graphic (clé inconnue, imbriqué, élément de liste) est une LACUNE : on ne peut pas prouver qu'il n'est pas affiché.
_OVERLAY_PLOT_KEYS = {"targetRatio", "maxValue", "slope", "intercept", "xMin", "xMax", "yMin", "yMax", "highlightX"}


def _pointer(*parts) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


MAX_DEPTH = 16  # au-delà, une structure n'est pas analysable de façon fiable : lacune de couverture, jamais récursion non bornée


def _has_content(value) -> bool:
    """Vrai si `value` peut porter du contenu potentiellement affiché : texte non vide, nombre (hors booléen), structure trop profonde,
    clé non textuelle ou type inattendu (tout ce qui n'est pas None/booléen/vide). Itératif : aucune récursion, donc aucune RecursionError."""
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DEPTH:
            return True
        if isinstance(node, str):
            if node.strip():
                return True
        elif isinstance(node, bool) or node is None:
            continue
        elif isinstance(node, (int, float)):
            return True
        elif isinstance(node, dict):
            if any(not isinstance(k, str) for k in node):
                return True
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend((v, depth + 1) for v in node)
        else:
            return True  # type inattendu : on ne peut pas prouver qu'il n'est pas affiché
    return False


def _collect_overlay(node, path: tuple) -> tuple[list[tuple[str, str]], list[str]]:
    """Tous les textes VISIBLES d'un `motion_graphic`, quelle que soit sa forme (objet, liste, imbriqué) : ([(pointeur JSON, texte)], lacunes).

    Une valeur qui n'est ni texte, ni conteneur, ni nombre sous `value` (type inattendu, clé non textuelle, profondeur > MAX_DEPTH) est une
    LACUNE : elle est consignée, jamais ignorée. Ordre du document conservé, sans récursion.
    """
    items: list[tuple[str, str]] = []
    gaps: list[str] = []
    stack = [(node, path, 0, None)]  # (valeur, chemin, profondeur, clé la plus proche : celle d'une liste est celle de son parent)
    while stack:
        current, where, depth, key = stack.pop()
        if depth > MAX_DEPTH:
            gaps.append(_pointer(*where))
        elif isinstance(current, str):
            if current.strip():
                items.append((_pointer(*where), current))
        elif isinstance(current, dict):
            children = []
            for child_key, value in current.items():
                if not isinstance(child_key, str):
                    gaps.append(_pointer(*where, repr(child_key)))
                elif child_key.startswith("_") or child_key in _OVERLAY_SKIP_KEYS:
                    continue
                else:
                    children.append((value, where + (child_key,), depth + 1, child_key))
            stack.extend(reversed(children))
        elif isinstance(current, (list, tuple)):
            stack.extend(reversed([(item, where + (i,), depth + 1, key) for i, item in enumerate(current)]))
        elif current is None or isinstance(current, bool):
            continue  # null et booléen : aucun texte à afficher
        elif isinstance(current, (int, float)):
            if key in _OVERLAY_NUMBER_KEYS:
                items.append((_pointer(*where), str(current)))          # chiffre affiché : lu comme texte
            elif key in _OVERLAY_PLOT_KEYS:
                continue                                                  # paramètre de tracé connu (display_text._NUMBER_FIELDS)
            else:
                gaps.append(_pointer(*where))  # nombre sous une clé inconnue (ou orphelin) : potentiellement affiché, non interprété
        else:
            gaps.append(_pointer(*where))  # type inattendu (bytes, objet...) : non analysable
    return items, gaps


def from_standard(script: dict, **ctx) -> dict:
    """Standard : titre + `blocks[i].text` + TOUT texte affiché des `motion_graphic` (unités `on_screen`). `declared_role` conserve
    le rôle étiqueté (un `cta` hérité reste une étiquette).

    Couverture : si un bloc porte une clé hors liste d'autorisation avec du texte, ou si `motion_graphic` n'est pas un objet/une liste,
    la lacune est consignée dans `coverage_gaps` (hashée) et la décision ne peut jamais être `accept`. Les autres champs du script
    (hashtags, stratégie de contenu...) ne sont pas affichés dans la vidéo et ne sont pas lus.
    """
    if not isinstance(script, dict) or not isinstance(script.get("blocks"), list):
        raise c.ReviewError(c.UNSUPPORTED_FORMAT, "a standard script needs a blocks list")
    units, gaps = [], []
    if isinstance(script.get("title"), str) and script["title"].strip():
        units.append(_unit("title", "/title", "title", script["title"]))
    elif _has_content(script.get("title")):
        gaps.append("/title")  # un titre qui n'est pas un texte exploitable (liste, nombre...) n'est pas lu : lacune
    for i, b in enumerate(script["blocks"]):
        if not isinstance(b, dict) or not isinstance(b.get("text"), str):
            raise c.ReviewError(c.UNSUPPORTED_FORMAT, f"blocks[{i}] has no text")
        bid = f"block-{i + 1:04d}"
        units.append(_unit(bid, f"/blocks/{i}/text", "spoken", b["text"], declared_role=b.get("role")))
        _read_overlay(b.get("motion_graphic"), ("blocks", i, "motion_graphic"), bid, units, gaps)
        gaps += [_pointer("blocks", i, key) if isinstance(key, str) else _pointer("blocks", i, repr(key))
                 for key, value in b.items() if key not in _STANDARD_NON_VIEWER_KEYS and (not isinstance(key, str) or _has_content(value))]
    # Racine du script : le texte affiché n'est PAS réservé aux blocs. Un overlay racine est lu ; toute autre clé racine hors liste
    # d'autorisation qui porte du contenu est une lacune. Liste d'autorisation = champs du contrat Standard (`engine/script.py`) qui ne
    # sont pas affichés dans la vidéo (métadonnées de génération, entrées, publication, choix de rendu).
    for key, value in script.items():
        if not isinstance(key, str):
            gaps.append(_pointer(repr(key)))
        elif key in _ROOT_OVERLAY_KEYS:
            _read_overlay(value, (key,), "root", units, gaps)
        elif key not in _ROOT_READ_OR_NON_VIEWER_KEYS and _has_content(value):
            gaps.append(_pointer(key))
    return build_snapshot(source_format="standard", units=units, coverage_gaps=gaps, **ctx)


def _read_overlay(node, path: tuple, unit_prefix: str, units: list, gaps: list) -> None:
    """Lit un `motion_graphic` (bloc ou racine) dans `units`/`gaps`. Une forme qui n'est ni objet ni liste est une lacune (jamais ignorée)."""
    if node is None:
        return
    if not isinstance(node, (dict, list, tuple)):
        gaps.append(_pointer(*path))
        return
    items, found = _collect_overlay(node, path)
    gaps.extend(found)
    start = 1 + sum(1 for u in units if u["unit_id"].startswith(f"{unit_prefix}:on_screen-"))
    for n, (pointer, text) in enumerate(items, start=start):
        units.append(_unit(f"{unit_prefix}:on_screen-{n:02d}", pointer, "on_screen", text, native_id=None))


def from_story_dialogue(script: dict, **ctx) -> dict:
    """Story dialogué : `story.shots[i].dialogue`, id natif et locuteur conservés, AUCUN narrateur ajouté."""
    story = script.get("story") if isinstance(script, dict) else None
    if not isinstance(story, dict) or not isinstance(story.get("shots"), list):
        raise c.ReviewError(c.UNSUPPORTED_FORMAT, "a story script needs story.shots")
    units = []
    for i, shot in enumerate(story["shots"]):
        if not isinstance(shot, dict) or not isinstance(shot.get("dialogue"), str):
            raise c.ReviewError(c.UNSUPPORTED_FORMAT, f"story.shots[{i}] has no dialogue")
        native = shot.get("id") if isinstance(shot.get("id"), str) else None
        units.append(_unit(native or f"shot-{i + 1:04d}", f"/story/shots/{i}/dialogue", "spoken", shot["dialogue"],
                           native_id=native, speaker_id=shot.get("speaker_id")))
    return build_snapshot(source_format="story_dialogue", units=units, **ctx)


FACTUALITY_TO_MODES = {  # `factuality` (schéma Story Visual v1), jamais `story_type` seul
    "verified": ("fact", "none"), "inspired": ("inspired", "none"), "fiction": ("fiction", "none"),
    "metaphor": ("fiction", "metaphor"),
}


def from_story_visual(plan: dict, **ctx) -> dict:
    """Story Visual v1 : titre, `scenes[i].narration` et `on_screen_text`. Les prompts d'image ne sont PAS de la narration.

    Le plan est lu comme JSON ; ce module n'importe pas `story_visual` (indépendant de la PR #103).
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list) or plan.get("factuality") not in FACTUALITY_TO_MODES:
        raise c.ReviewError(c.UNSUPPORTED_FORMAT, "a story_visual plan needs scenes and a valid factuality")
    truth, illustration = FACTUALITY_TO_MODES[plan["factuality"]]
    ctx.setdefault("truth_mode", truth)
    ctx.setdefault("illustration_mode", illustration)
    units = []
    if isinstance(plan.get("title"), str) and plan["title"].strip():
        units.append(_unit("title", "/title", "title", plan["title"]))
    for i, scene in enumerate(plan["scenes"]):
        if not isinstance(scene, dict) or not isinstance(scene.get("narration"), str):
            raise c.ReviewError(c.UNSUPPORTED_FORMAT, f"scenes[{i}] has no narration")
        sid = scene.get("id") if isinstance(scene.get("id"), str) else f"scene-{i + 1:04d}"
        units.append(_unit(f"{sid}:narration", f"/scenes/{i}/narration", "spoken", scene["narration"], native_id=sid,
                           declared_role=scene.get("beat")))
        if isinstance(scene.get("on_screen_text"), str) and scene["on_screen_text"].strip():
            units.append(_unit(f"{sid}:on_screen", f"/scenes/{i}/on_screen_text", "on_screen", scene["on_screen_text"], native_id=sid))
    return build_snapshot(source_format="story_visual", units=units, **ctx)


READ_LIMITS = {"standard": [], "story_dialogue": [], "story_visual": ["image_prompts_not_evidence"]}


def adapt(kind: str, document: dict, **ctx) -> dict:
    """Routage explicite. Quiz, AutoEdit et tout format inconnu sont refusés (leur routage actuel reste inchangé)."""
    adapters = {"standard": from_standard, "story_dialogue": from_story_dialogue, "story_visual": from_story_visual}
    if kind not in adapters:
        raise c.ReviewError(c.UNSUPPORTED_FORMAT, f"unsupported format {kind!r}")
    return adapters[kind](document, **ctx)
