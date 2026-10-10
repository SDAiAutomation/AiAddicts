"""Versionne les artefacts générés pour éviter les rendus périmés."""
import hashlib
import json
import os
from pathlib import Path


_GENERATION_MODULES = (
    "assembler.py", "captions.py", "editorial_quality.py", "generation_cache.py", "quiz.py", "quiz_cover.py",
    "image_character_bible.py",
    "image_model_router.py", "image_prompt_builder.py", "image_style_bible.py",
    "openai_images.py", "quality.py", "stock_planner.py", "tts.py",
    "kinetic_typography.py",
    "motion_graphics/animations.py", "motion_graphics/canvas.py", "motion_graphics/display_text.py", "motion_graphics/layout.py",
    "motion_graphics/preflight.py", "motion_graphics/renderer.py", "motion_graphics/scenes.py",
    "motion_graphics/schema.py", "motion_graphics/semantic.py", "motion_graphics/sync.py", "motion_graphics/theme.py", "video.py", "visuals.py",
)

_GENERATION_ENV = (
    "IMAGE_MODEL_PREMIUM", "IMAGE_FINAL_QUALITY", "OPENAI_IMAGE_MODEL",
    "OPENAI_IMAGE_QUALITY", "IMAGE_QC_ENABLED", "IMAGE_QC_MODEL",
    "MAX_IMAGE_ATTEMPTS", "SUBTITLE_FONT", "VISUALS_BLOCKS_PER_IMAGE",
)


def _code_digest() -> str:
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for name in _GENERATION_MODULES:
        path = root / name
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


# Champs DÉRIVÉS écrits par le moteur dans le script après un rendu
# (engine/retention.py). Ils ne pilotent aucun rendu : les hasher invaliderait
# le cache (images/voix payantes) à chaque régénération d'un script déjà rendu.
_DERIVED_SCRIPT_KEYS = ("retentionDiagnostics", "generationMetadata")


def fingerprint(script: dict, voice_id: str) -> str:
    """Empreinte stable du contenu et de tout ce qui influence le rendu."""
    script = {k: v for k, v in script.items() if k not in _DERIVED_SCRIPT_KEYS}
    payload = {
        "script": script,
        "voice_id": voice_id,
        "settings": {name: os.environ.get(name) for name in _GENERATION_ENV},
        "code": _code_digest(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
