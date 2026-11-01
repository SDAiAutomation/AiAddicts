"""Orchestration des illustrations : cache -> budget -> fournisseur injecté -> manifeste de reprise.

Le fournisseur est UNE fonction injectée. `openai_provider()` enveloppe l'intégration existante
(`engine.openai_images` + `image_model_router`, coûts compris) ; il n'est jamais appelé par les tests ni par l'exemple.
Exécution idempotente : un manifeste par (locataire, histoire) mémorise l'état de chaque scène ; relancer ne
regénère que les scènes `failed`/absentes. Régénérer UNE scène n'invalide que celle-là.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import image_model_router, openai_images
from . import cache as cache_mod
from . import cost, schema, store, visual_direction

_SAFE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class RegenerationLimit(RuntimeError):
    """Plafond de régénérations atteint pour la scène ou pour l'histoire (chaque régénération est payante)."""


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


@dataclass
class ImageResult:
    path: str | None
    cost_usd: float | None = None
    usage: dict | None = None
    error: str | None = None


Provider = Callable[..., ImageResult]


def openai_provider() -> Provider:
    """Adaptateur vers l'intégration EXISTANTE (clé serveur, retry, limite de débit, usage réel). PAYANT."""
    def call(prompt: str, out_path: str, *, model: str, quality: str, reference_path: str | None = None) -> ImageResult:
        if reference_path:
            path = openai_images.edit_image(prompt, reference_path, out_path, model, quality, "9:16")
        else:
            path = openai_images.generate_image(prompt, out_path, "9:16", None, model, quality)
        usage = openai_images.pop_last_usage() if path else None
        error = None if path else openai_images.pop_last_error()
        return ImageResult(path, image_model_router.estimate_cost_or_none(model, quality, usage) if path else 0.0, usage, error)
    return call


MAX_ATTEMPTS_PER_SCENE = 3     # au-delà : `needs_review` (revue humaine), plus aucun appel automatique
MAX_IMAGE_PIXELS = 36_000_000  # refuse une « bombe de décompression » renvoyée par un fournisseur
MIN_IMAGE_SIDE = 512


def _manifest_path(work_dir: Path, tenant_id: str, story_id: str) -> Path:
    if not _SAFE.fullmatch(tenant_id) or not _SAFE.fullmatch(story_id):
        raise ValueError("invalid tenant or story id")
    directory = Path(work_dir).resolve() / tenant_id / story_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "images.json"


def check_image(path: str | Path) -> str | None:
    """None si l'image est exploitable, sinon le motif. Vérifie format, décodage, taille ; ne la charge pas en entier d'abord."""
    from PIL import Image
    try:
        with Image.open(path) as img:
            if img.format not in ("JPEG", "PNG", "WEBP"):
                return "invalid_image_format"
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                return "image_too_large"
            if min(width, height) < MIN_IMAGE_SIDE:
                return "image_too_small"
            img.verify()
    except Exception:  # noqa: BLE001 - tout fichier illisible est refusé
        return "invalid_image"
    return None


def generate_scene_images(plan: dict, *, tenant_id: str, work_dir: str | Path, provider: Provider,
                          tracker: cost.BudgetTracker, expected_unit_usd: float | None,
                          disk_cache: cache_mod.DiskImageCache | None = None, only: set[str] | None = None,
                          force: set[str] | None = None, max_scene_regenerations: int | None = None,
                          max_story_regenerations: int | None = None) -> dict:
    """Retourne `{scene_id: {status, path, cost_usd, cost_kind, cache_hit, error, generations, attempts}}`.

    Le plan est REVALIDÉ ici (fail-closed : un identifiant de scène hostile ne devient jamais un chemin). Un échec fournisseur
    (statut `failed`, exception comprise) est enregistré et reprenable ; après `MAX_ATTEMPTS_PER_SCENE` essais la scène passe en
    `needs_review`. Lève `BudgetExceeded` AVANT un appel payant qui dépasserait le plafond, `RegenerationLimit` au-delà des plafonds de
    régénération, `JobBusy` si une autre exécution tient l'histoire, `ManifestCorrupt` si le manifeste est illisible. La dépense déjà
    faite (manifeste) est reprise dans `tracker` : relancer ou régénérer ne remet jamais le budget à zéro."""
    errors = schema.validate_story_plan(plan)
    if errors:
        raise ValueError("invalid plan: " + "; ".join(errors[:3]))
    selection = image_model_router.select_model("final")
    manifest_path = _manifest_path(Path(work_dir), tenant_id, plan["story_id"])
    with store.job_lock(manifest_path.parent):
        return _generate(plan, selection, manifest_path, tenant_id, provider, tracker, expected_unit_usd, disk_cache, only,
                         force or set(), max_scene_regenerations, max_story_regenerations)


def _generate(plan, selection, manifest_path, tenant_id, provider, tracker, expected_unit_usd, disk_cache, only, force,
              max_scene_regenerations, max_story_regenerations) -> dict:
    manifest = store.load_manifest(manifest_path)
    for sid, entry in manifest.items():  # dépense déjà faite : reprise dans le budget de l'épisode
        if isinstance(entry, dict) and entry.get("status") == "done":
            tracker.seed(f"image:{sid}", entry.get("cost_usd"), entry.get("cost_kind", cost.MEASURED))
    per_scene = _int_env("STORY_MAX_SCENE_REGENERATIONS", 2) if max_scene_regenerations is None else max_scene_regenerations
    per_story = _int_env("STORY_MAX_STORY_REGENERATIONS", 6) if max_story_regenerations is None else max_story_regenerations
    used = sum(max(0, m.get("generations", 0) - 1) for m in manifest.values() if isinstance(m, dict))
    images_dir = manifest_path.parent
    for index, scene in enumerate(plan["scenes"]):
        sid = scene["id"]
        if only is not None and sid not in only:
            continue
        prompt = visual_direction.build_image_prompt(plan, index)
        key = cache_mod.image_key(tenant_id, prompt, selection.model, selection.quality, direction=plan["art_direction"])
        out = images_dir / f"{sid}.jpg"
        previous = manifest.get(sid) or {}
        generations, attempts = previous.get("generations", 0), previous.get("attempts", 0)
        if sid not in force and previous.get("status") == "done" and previous.get("key") == key and out.is_file():
            continue  # idempotent : rien à refaire
        if sid not in force and previous.get("status") == "needs_review" and previous.get("key") == key:
            continue  # épuisée : décision humaine (régénération explicite) requise
        if sid not in force and disk_cache and disk_cache.restore(key, out) and check_image(out) is None:
            manifest[sid] = {"status": "done", "path": str(out), "key": key, "cost_usd": 0.0, "cost_kind": cost.CACHED,
                             "cache_hit": True, "error": None, "generations": generations, "attempts": attempts}
            tracker.seed(f"image:{sid}", 0.0, cost.CACHED)
        else:
            # toute nouvelle image pour une scène déjà générée (régénération ou prompt modifié) est plafonnée
            if generations >= 1:
                if generations - 1 >= per_scene or used >= per_story:
                    raise RegenerationLimit(f"{sid}: regeneration limit reached ({per_scene} per scene, {per_story} per story)")
            if previous.get("key") != key or sid in force:
                attempts = 0  # nouvelle demande : le compteur d'échecs repart
            item = f"image:{sid}"
            tracker.reserve(item, expected_unit_usd)
            if generations >= 1:
                used += 1
            attempts += 1
            try:
                result = provider(prompt, str(out), model=selection.model, quality=selection.quality)
            except Exception as exc:  # noqa: BLE001 - un fournisseur qui lève a peut-être été facturé : coût inconnu, scène en échec
                tracker.record(item, None)
                result = ImageResult(None, None, None, f"provider_exception:{type(exc).__name__}")
            else:
                reason = None
                if result.path and Path(result.path).resolve() != out.resolve():
                    reason = "unexpected_output_path"
                elif result.path and Path(result.path).is_file():
                    reason = check_image(out)
                elif result.path:
                    reason = "missing_output"
                if result.path and reason is None:
                    kind = cost.MEASURED if result.cost_usd is not None else cost.UNPRICED
                    tracker.record(item, result.cost_usd, kind)
                    if disk_cache:
                        disk_cache.save(key, out)
                    manifest[sid] = {"status": "done", "path": str(out), "key": key, "cost_usd": result.cost_usd,
                                     "cost_kind": kind, "cache_hit": False, "error": None,
                                     "generations": generations + 1, "attempts": attempts}
                    store.save_manifest(manifest_path, manifest)
                    continue
                # échec : le fournisseur peut avoir facturé des tentatives internes -> coût inconnu, jamais « 0 $ certain »
                tracker.record(item, None)
                result = ImageResult(None, None, None, reason or result.error or "unknown")
            status = "needs_review" if attempts >= MAX_ATTEMPTS_PER_SCENE else "failed"
            manifest[sid] = {"status": status, "path": None, "key": key, "cost_usd": None, "cost_kind": cost.UNPRICED,
                             "cache_hit": False, "error": result.error or "unknown", "generations": generations,
                             "attempts": attempts}
        store.save_manifest(manifest_path, manifest)
    return manifest


def regenerate_scene(plan: dict, scene_id: str, **kwargs) -> dict:
    """Régénère UNE image (ex. bouton « régénérer cette image »), sans toucher aux autres scènes."""
    return generate_scene_images(plan, only={scene_id}, force={scene_id}, **kwargs)
