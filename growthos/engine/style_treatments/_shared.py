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


# Marge de sécurité pour tout élément dessiné (bordure, cadre, texte) qui doit
# SURVIVRE le pipeline de rendu final, pas seulement paraître correct sur
# l'image traitée isolée. Mesuré empiriquement (Phase 3, QA vidéo finale) :
# engine/video.py applique d'abord un crop "aspect ratio increase" (~7.8% de
# chaque côté pour une image source 1024x1536 vers une sortie 1080x1920), PUIS
# un zoom Ken Burns pouvant monter à 1.28x — un élément à moins de ~10% du
# bord d'origine est quasi systématiquement rogné avant la fin du plan. 14%
# reprend la marge du détail encadré d'INSET_PANEL (comic.py), déjà vérifiée
# visible sur une vraie vidéo rendue.
SAFE_EDGE_MARGIN_RATIO = 0.14


def safe_margin(size: tuple[int, int]) -> int:
    return round(min(size) * SAFE_EDGE_MARGIN_RATIO)


def draw_rect_border(img: Image.Image, color: tuple[int, int, int], width: int | None = None) -> Image.Image:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    bw = width if width is not None else border_width(img.size)
    for i in range(bw):
        draw.rectangle((i, i, w - 1 - i, h - 1 - i), outline=color)
    return img


def draw_inset_border(
    img: Image.Image, color: tuple[int, int, int], margin: int | None = None, width: int | None = None
) -> Image.Image:
    """Comme `draw_rect_border`, mais la ligne est tracée à `margin` px du
    bord plutôt que flush contre le bord — voir `safe_margin` : une bordure
    flush contre le bord est quasi toujours rognée par le crop d'aspect ratio
    + le zoom Ken Burns du pipeline de rendu final (engine/video.py)."""
    w, h = img.size
    m = margin if margin is not None else safe_margin(img.size)
    bw = width if width is not None else border_width(img.size)
    draw = ImageDraw.Draw(img)
    for i in range(bw):
        draw.rectangle((m + i, m + i, w - 1 - m - i, h - 1 - m - i), outline=color)
    return img
