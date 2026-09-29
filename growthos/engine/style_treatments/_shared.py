"""Helpers Pillow partagés entre `comic.py` et `game_art.py` — Phase 3.

Rien ici n'appelle de fournisseur externe ni ne touche à la résolution finale
1080x1920 : chaque traitement opère à la résolution NATIVE de l'image de
scène déjà générée (par ex. ~1024x1536 côté OpenAI) et rend un `.jpg` du même
rôle. Le cadrage/zoom final (Ken Burns) reste entièrement géré par
`engine/video.py`, inchangé."""
from __future__ import annotations

from PIL import Image, ImageDraw


def center_crop(img: Image.Image, ratio: float) -> Image.Image:
    """Recadrage centré à `ratio` (0-1) de la taille d'origine, ré-agrandi à
    la taille d'origine — un "punch-in" / détail sans regénérer d'image."""
    w, h = img.size
    cw, ch = max(1, round(w * ratio)), max(1, round(h * ratio))
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return img.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.LANCZOS)


def border_width(size: tuple[int, int]) -> int:
    return max(4, round(min(size) * 0.012))


def draw_rect_border(img: Image.Image, color: tuple[int, int, int], width: int | None = None) -> Image.Image:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    bw = width if width is not None else border_width(img.size)
    for i in range(bw):
        draw.rectangle((i, i, w - 1 - i, h - 1 - i), outline=color)
    return img
