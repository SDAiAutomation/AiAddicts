"""Carte d'illustration 1080x1920 (recadrage « cover », JPEG), SANS texte.

Le texte à l'écran n'est plus dessiné ici : les sous-titres sont ceux de Faceloop (`engine/captions.py`), incrustés au rendu
(`render.render_story(captions_ass=...)`). Le champ `on_screen_text` reste dans le plan mais n'est pas affiché.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

W, H = 1080, 1920
MAX_INPUT_PIXELS = 36_000_000


def compose_card(image_path: str | Path, out_path: str | Path) -> None:
    with Image.open(image_path) as probe:
        if probe.width * probe.height > MAX_INPUT_PIXELS or probe.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("illustration refused: unsupported format or too many pixels")
        image = probe.convert("RGB")
    scale = max(W / image.width, H / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - W) // 2, (image.height - H) // 2
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    image.crop((left, top, left + W, top + H)).save(out_path, "JPEG", quality=92)
