"""Generate the illustration used by the opening cover of a quiz video."""
import os
from pathlib import Path

from . import openai_images


def generate_cover(script: dict, work_dir: Path) -> str | None:
    quiz = script.get("quiz") or {}
    cover = quiz.get("cover") or {}
    if not cover.get("enabled"):
        return None
    out = work_dir / "images" / "quiz-cover.png"
    if out.exists() and out.stat().st_size > 0:
        return str(out)
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    category = str(cover.get("category") or quiz.get("topic") or "general knowledge")
    colour = str(cover.get("color") or "electric blue")
    prompt = (
        f"Vertical 9:16 editorial cover illustration for a {category} quiz, dominant {colour}. "
        "A friendly original cartoon brain mascot with expressive eyes, confident pose, "
        "surrounded by a few clean thematic symbols. Bold simple composition, high contrast, "
        "premium social media design, large empty area in the upper-middle for a title. "
        "Keep the bottom 20 percent visually quiet and free of important elements. "
        "No words, no letters, no logos, no watermark, no human presenter."
    )
    return openai_images.generate_image(prompt, str(out), "9:16")
