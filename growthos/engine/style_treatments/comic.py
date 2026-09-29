"""Comic Book style treatment — Phase 3 (distinctive style engines).

Une passe de compositing Pillow DÉTERMINISTE appliquée à une image de scène
déjà générée (fraîche ou réutilisée d'un bloc voisin, voir Phase 2.6's
`is_style_integrity_preserved` : le traitement s'applique quelle que soit
l'origine du fichier source — jamais de nouvel appel image). La sortie est un
`.jpg` de même rôle, même résolution native, qui repart tel quel dans le
pipeline Ken Burns / rendu existant (engine/video.py, INCHANGÉ) — ce module
n'est qu'une couche de composition, pas un second assembleur.

Vocabulaire de mise en page (petit, déterministe, choisi depuis les
métadonnées Phase 1 shotType/visualPurpose — jamais aléatoire) :

- FULL_PANEL       : plan large ou une scène de révélation/paiement — l'image
                      pleine, traitée, sans recadrage additionnel.
- SINGLE_PANEL      : gros plan — un punch-in modéré (86% recadré) + bordure.
- INSET_PANEL       : plan d'insert — un fond flouté/assombri de la MÊME
                      image derrière un détail net encadré (aucune 2e image).
- SPLIT_HORIZONTAL  : plan moyen + action — deux bandes, deux recadrages
                      DIFFÉRENTS de la MÊME image (contexte en haut, détail
                      d'action en bas) — la "planche" comic sans nouvelle
                      génération.

Traitement graphique : contraste/saturation légers + accentuation façon
encrage + trame de points (halftone) très subtile + bordure d'encre — visé
« bande dessinée premium », jamais le filtre Instagram-comic agressif."""
from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from ._shared import border_width, center_crop, draw_rect_border

LAYOUTS = ("FULL_PANEL", "SINGLE_PANEL", "SPLIT_HORIZONTAL", "INSET_PANEL")

_INK_COLOR = (14, 14, 18)
_INK_CONTRAST = 1.12
_INK_SATURATION = 1.10
_HALFTONE_OPACITY = 20  # 0-255 — délibérément subtil, jamais un filtre criard


def select_layout(shot_type: str | None, visual_purpose: str | None) -> str:
    """Déterministe : le même couple (shotType, visualPurpose) choisit
    toujours la même mise en page — voir la section 18 du brief Phase 3
    ("Are borders/layouts useful rather than distracting?")."""
    if visual_purpose in ("reveal", "payoff"):
        return "FULL_PANEL"
    if shot_type == "wide":
        return "FULL_PANEL"
    if shot_type == "insert":
        return "INSET_PANEL"
    if shot_type == "medium" and visual_purpose == "action":
        return "SPLIT_HORIZONTAL"
    return "SINGLE_PANEL"


def _ink(img: Image.Image) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(_INK_CONTRAST)
    img = ImageEnhance.Color(img).enhance(_INK_SATURATION)
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=55, threshold=3))


def _halftone(img: Image.Image) -> Image.Image:
    """Trame de points sombres à opacité très faible — suggère l'encrage BD
    sans jamais assombrir franchement l'image (pas un filtre "sale photo")."""
    base = img.convert("RGBA")
    w, h = base.size
    tile = max(6, w // 110)
    dot = Image.new("L", (tile, tile), 0)
    ImageDraw.Draw(dot).ellipse(
        (tile * 0.18, tile * 0.18, tile * 0.82, tile * 0.82), fill=_HALFTONE_OPACITY
    )
    cols, rows = w // tile + 2, h // tile + 2
    pattern = Image.new("L", (cols * tile, rows * tile), 0)
    for cx in range(cols):
        for cy in range(rows):
            pattern.paste(dot, (cx * tile, cy * tile))
    pattern = pattern.crop((0, 0, w, h))
    ink_layer = Image.new("RGBA", (w, h), (*_INK_COLOR, 255))
    ink_layer.putalpha(pattern)
    return Image.alpha_composite(base, ink_layer).convert("RGB")


def _render_full_panel(img: Image.Image) -> Image.Image:
    return draw_rect_border(_halftone(_ink(img)), _INK_COLOR)


def _render_single_panel(img: Image.Image) -> Image.Image:
    return _render_full_panel(center_crop(img, 0.86))


def _render_inset_panel(img: Image.Image) -> Image.Image:
    w, h = img.size
    background = _ink(img).filter(ImageFilter.GaussianBlur(radius=max(2, w // 180)))
    background = ImageEnhance.Brightness(background).enhance(0.55)
    background = _halftone(background)
    detail = _ink(center_crop(img, 0.5))
    inset_w, inset_h = round(w * 0.72), round(h * 0.72)
    detail = detail.resize((inset_w, inset_h), Image.LANCZOS)
    canvas = background.copy()
    x0, y0 = (w - inset_w) // 2, (h - inset_h) // 2
    canvas.paste(detail, (x0, y0))
    bw = border_width((inset_w, inset_h))
    draw = ImageDraw.Draw(canvas)
    for i in range(bw):
        draw.rectangle(
            (x0 - i, y0 - i, x0 + inset_w - 1 + i, y0 + inset_h - 1 + i), outline=_INK_COLOR
        )
    return draw_rect_border(canvas, _INK_COLOR)


def _render_split_horizontal(img: Image.Image) -> Image.Image:
    w, h = img.size
    gutter = max(4, h // 160)
    band_h = (h - gutter) // 2
    top = _ink(img.resize((w, h), Image.LANCZOS)).resize((w, band_h), Image.LANCZOS)
    bottom = _ink(center_crop(img, 0.55)).resize((w, band_h), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), _INK_COLOR)
    canvas.paste(_halftone(top), (0, 0))
    canvas.paste(_halftone(bottom), (0, band_h + gutter))
    return draw_rect_border(canvas, _INK_COLOR)


_RENDERERS = {
    "FULL_PANEL": _render_full_panel,
    "SINGLE_PANEL": _render_single_panel,
    "INSET_PANEL": _render_inset_panel,
    "SPLIT_HORIZONTAL": _render_split_horizontal,
}


def apply(source_path: str, out_path: str, shot_type: str | None, visual_purpose: str | None) -> dict:
    """Lit `source_path`, applique le traitement comic déterministe, écrit
    `out_path` — `source_path` n'est JAMAIS modifié (voir la section 12 du
    brief : garder l'original pour le debug/la comparaison). Laisse
    l'exception remonter ; l'appelant (`engine.visuals._apply_style_treatments`)
    est responsable du repli sur l'image non traitée si ce traitement échoue."""
    t0 = time.monotonic()
    layout = select_layout(shot_type, visual_purpose)
    with Image.open(source_path) as img:
        img = img.convert("RGB")
        treated = _RENDERERS[layout](img)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        treated.save(out_path, "JPEG", quality=92)
    return {
        "styleTreatment": "comic",
        "layout": layout,
        "treatmentApplied": True,
        "processingTimeS": round(time.monotonic() - t0, 3),
    }
