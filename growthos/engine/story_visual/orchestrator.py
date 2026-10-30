"""Orchestration des illustrations : cache -> budget -> fournisseur injecté -> manifeste de reprise.

Le fournisseur est UNE fonction injectée. `openai_provider()` enveloppe l'intégration existante
(`engine.openai_images` + `image_model_router`, coûts compris) ; il n'est jamais appelé par les tests ni par l'exemple.
Exécution idempotente : un manifeste par (locataire, histoire) mémorise l'état de chaque scène ; relancer ne
regénère que les scènes `failed`/absentes. Régénérer UNE scène n'invalide que celle-là.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import asset_store, image_model_router, openai_images
from . import cache as cache_mod
from . import cost, visual_direction

_SAFE = re.compile(r"[A-Za-z0-9_-]{1,64}")


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
        return ImageResult(path, image_model_router.estimate_cost(model, quality, usage) if path else 0.0, usage, error)
    return call


def _manifest_path(work_dir: Path, tenant_id: str, story_id: str) -> Path:
    if not _SAFE.fullmatch(tenant_id) or not _SAFE.fullmatch(story_id):
        raise ValueError("invalid tenant or story id")
    directory = Path(work_dir).resolve() / tenant_id / story_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "images.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def generate_scene_images(plan: dict, *, tenant_id: str, work_dir: str | Path, provider: Provider,
                          tracker: cost.BudgetTracker, expected_unit_usd: float | None,
                          disk_cache: cache_mod.DiskImageCache | None = None, only: set[str] | None = None,
                          force: set[str] | None = None) -> dict:
    """Retourne `{scene_id: {status, path, cost_usd, cache_hit, error}}`. Ne lève pas sur un échec fournisseur
    (statut `failed`, reprise possible) ; lève `BudgetExceeded` AVANT un appel payant qui dépasserait le plafond.
    `only` limite aux scènes demandées ; `force` ignore cache et manifeste pour ces scènes (régénération ciblée)."""
    selection = image_model_router.select_model("final")
    manifest_path = _manifest_path(Path(work_dir), tenant_id, plan["story_id"])
    manifest = _load(manifest_path)
    force = force or set()
    images_dir = manifest_path.parent
    for index, scene in enumerate(plan["scenes"]):
        sid = scene["id"]
        if only is not None and sid not in only:
            continue
        prompt = visual_direction.build_image_prompt(plan, index)
        key = cache_mod.image_key(tenant_id, prompt, selection.model, selection.quality, direction=plan["art_direction"])
        out = images_dir / f"{sid}.jpg"
        previous = manifest.get(sid)
        if sid not in force and previous and previous.get("status") == "done" and previous.get("key") == key and out.is_file():
            continue  # idempotent : rien à refaire
        if sid not in force and disk_cache and disk_cache.restore(key, out):
            manifest[sid] = {"status": "done", "path": str(out), "key": key, "cost_usd": 0.0, "cache_hit": True, "error": None}
        else:
            tracker.reserve(f"image:{sid}", expected_unit_usd)
            result = provider(prompt, str(out), model=selection.model, quality=selection.quality)
            actual = result.cost_usd if result.cost_usd is not None else (expected_unit_usd or 0.0)
            if result.path and Path(result.path).is_file():
                tracker.record(f"image:{sid}", actual)
                if disk_cache:
                    disk_cache.save(key, result.path)
                manifest[sid] = {"status": "done", "path": result.path, "key": key, "cost_usd": actual, "cache_hit": False, "error": None}
            else:
                manifest[sid] = {"status": "failed", "path": None, "key": key, "cost_usd": 0.0, "cache_hit": False,
                                 "error": result.error or "unknown"}
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def regenerate_scene(plan: dict, scene_id: str, **kwargs) -> dict:
    """Régénère UNE image (ex. bouton « régénérer cette image »), sans toucher aux autres scènes."""
    return generate_scene_images(plan, only={scene_id}, force={scene_id}, **kwargs)
