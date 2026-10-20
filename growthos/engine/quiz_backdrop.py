"""Fond illustré d'un quiz long : une image de sujet par partie, en bichromie.

Un quiz long de 25 questions n'a pas de budget pour 25 illustrations ; quatre images (une par partie, voir
`quiz_motion.PARTS`) donnent un fond vivant sans multiplier le coût. Chaque image est passée en bichromie aux
couleurs de la partie : le texte reste lisible quelle que soit l'image (le contraste est borné par construction,
la lumière n'éclaircit la teinte que de 22 %), et l'identité de chaque partie est conservée.

Facultatif et jamais bloquant : `quiz.backdrops` doit valoir vrai, la clé API être présente ; un échec laisse
simplement le fond uni de la partie (voir `engine/openai_images.py`)."""
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from . import openai_images, quiz_motion

SIZE = (1920, 1080)
# Une variante par partie : quatre images voisines mais pas identiques.
_VARIANTS = (
    "a detailed macro close-up of typical objects of the subject",
    "a wide atmospheric scene of the subject",
    "a still life of characteristic tools and materials of the subject",
    "a dramatic moody close-up with strong directional light",
    "a richly textured symbolic scene of advanced discovery",
)
_PROMPT = (
    "Editorial photograph evoking the subject of a general-knowledge quiz about {topic}: {variant}. "
    "Wide 16:9 composition with calm negative space, soft depth of field. "
    "No text, no letters, no numbers, no logos, no watermark, no people."
)


def enabled(script: dict) -> bool:
    quiz = script.get("quiz") or {}
    return (script.get("content_format") == "quiz" and quiz.get("recipe") == "long"
            and quiz.get("presentation") == "motion" and quiz.get("backdrops") is True)


def duotone(source: str, out_path: str, stage: str, light: bool = False) -> str:
    """Image en niveaux de gris, ramenée entre deux tons de la couleur de scène ; JPEG 1920x1080."""
    image = ImageOps.fit(Image.open(source).convert("L"), SIZE, Image.Resampling.LANCZOS)
    image = ImageOps.autocontrast(image.filter(ImageFilter.GaussianBlur(2)), cutoff=1)
    low, high = ((quiz_motion._mix_hex(stage, "#000000", .10), stage) if light
                 else (stage, quiz_motion._mix_hex(stage, "#ffffff", .22)))
    colour = ImageOps.colorize(image, black=low, white=high)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    colour.save(out_path, "JPEG", quality=88)
    return out_path


def generate(script: dict, work_dir: Path) -> list[str | None]:
    """Chemins des fonds, un par partie (None si la génération a échoué ou est indisponible)."""
    quiz = script.get("quiz") or {}
    theme = quiz.get("theme")
    topic = str(quiz.get("topic") or script.get("title") or "general knowledge")
    light = theme in quiz_motion._LIGHT_THEMES
    results: list[str | None] = []
    parts = quiz_motion.FIVE_LEVEL_PARTS if quiz.get("chapter_mode") == "five_levels" else quiz_motion.PARTS
    for part in range(parts):
        out = Path(work_dir) / "images" / f"quiz-backdrop-{part}.jpg"
        if out.exists() and out.stat().st_size > 0:
            results.append(str(out))
            continue
        raw = openai_images.generate_image(
            _PROMPT.format(topic=topic, variant=_VARIANTS[part]), str(Path(work_dir) / "images" / f"quiz-backdrop-{part}-raw.jpg"),
            "16:9", quality="low",
        )
        if not raw:
            results.append(None)
            continue
        try:
            results.append(duotone(raw, str(out), quiz_motion.stage_background(theme, part, parts), light))
        except Exception as exc:  # image illisible : le fond uni reste
            print(f"       fond illustré {part + 1} inutilisable ({exc})")
            results.append(None)
    return results
