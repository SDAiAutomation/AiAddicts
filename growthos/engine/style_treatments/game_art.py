"""Game Loading Screen style treatment — Phase 3 (distinctive style engines).

L'id interne reste `gta_loading` (compatibilité scripts/scènes existants,
voir `apply()` et `engine/image_style_bible.py`) mais l'identité visuelle
n'imite AUCUN jeu précis : pas de typographie/logo/mise en page copiés —
seulement une identité "clé d'art jeu vidéo stylisée" originale (cadrage
poster, vignette marquée, contraste graphique, cadre décoratif sobre,
motif de chargement minimal occasionnel) — délibérément distincte d'anime.

Comme `comic.py`, ce module ne fait QUE lire une image de scène déjà
générée et écrire un `.jpg` traité de même rôle/résolution — aucun appel
IA, aucune modification de `engine/video.py`. La pseudo-profondeur demandée
par le brief (section 10) est déjà couverte par le Ken Burns existant
(profil de mouvement `energetic`, voir `image_style_bible._STYLE_IDENTITY`)
appliqué PAR-DESSUS ce traitement statique — pas de mécanisme de parallax
séparé (une vraie parallax demanderait une segmentation IA, explicitement
exclue du brief)."""
from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from ._shared import draw_rect_border

# Or/laiton sobre, générique "clé d'art jeu vidéo" — jamais la palette d'une
# franchise précise.
_FRAME_COLOR = (198, 168, 92)
_TRACK_COLOR = (80, 80, 86)
_VIGNETTE_STRENGTH = 0.55
_POSTERIZE_BITS = 5
# Zone sûre sous-titres (engine/motion_graphics/canvas.py::SAFE_BOTTOM_RATIO)
# = 30% du bas — le motif reste nettement au-dessus.
_LOADING_Y_RATIO = 0.66


def wants_loading_motif(shot_type: str | None, visual_purpose: str | None) -> bool:
    """Déterministe et volontairement rare (section 9 du brief) : seuls les
    tout premiers plans d'une vidéo se lisent naturellement comme un
    "chargement" — pas les plans d'action normaux."""
    return visual_purpose in ("hook", "establish")


def _vignette(img: Image.Image) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = w / 2, h / 2
    max_r = (cx ** 2 + cy ** 2) ** 0.5
    # Anneaux concentriques du bord (sombre) vers le centre (clair) — pas
    # besoin d'un vrai dégradé radial pixel par pixel pour un effet sobre.
    steps = 40
    for i in range(steps, -1, -1):
        r = max_r * i / steps
        level = int(255 * (1 - _VIGNETTE_STRENGTH * (1 - i / steps)))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=level)
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, dark, mask)


def _poster_contrast(img: Image.Image) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(1.18)
    img = ImageEnhance.Color(img).enhance(1.05)
    return ImageOps.posterize(img, _POSTERIZE_BITS)


def _frame(img: Image.Image) -> Image.Image:
    w, h = img.size
    margin = max(10, round(min(w, h) * 0.035))
    outer_w = max(3, round(min(w, h) * 0.006))
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        (margin, margin, w - 1 - margin, h - 1 - margin), outline=_FRAME_COLOR, width=outer_w
    )
    return img


def _loading_motif(img: Image.Image) -> Image.Image:
    w, h = img.size
    draw = ImageDraw.Draw(img)
    font_size = max(16, round(h * 0.024))
    font = ImageFont.load_default(size=font_size)
    label = "LOADING"
    margin = max(24, round(h * 0.045))
    y = round(h * _LOADING_Y_RATIO)
    draw.text((margin, y), label, font=font, fill=_FRAME_COLOR, anchor="lm")
    label_w = draw.textlength(label, font=font)
    bar_x0 = margin + label_w + margin * 0.6
    bar_x1 = w - margin
    bar_w = max(2, font_size // 8)
    draw.line((bar_x0, y, bar_x1, y), fill=_TRACK_COLOR, width=bar_w)
    draw.line((bar_x0, y, bar_x0 + (bar_x1 - bar_x0) * 0.62, y), fill=_FRAME_COLOR, width=bar_w)
    return img


def apply(source_path: str, out_path: str, shot_type: str | None, visual_purpose: str | None) -> dict:
    """Même contrat que `comic.apply` : `source_path` n'est jamais modifié,
    la sortie est un `.jpg` traité prêt pour le pipeline de rendu existant.
    Note de portée (voir le rapport Phase 3) : le motif de chargement est ici
    un repère STATIQUE incrusté dans l'image traitée (le Ken Burns appliqué
    ensuite lui donne un peu de vie) plutôt qu'un clip animé séparé — une
    vraie animation aurait exigé une 2e piste de rendu image-par-image pour
    un gain visuel marginal, hors de la portée "traitement de compositing
    léger" du brief."""
    t0 = time.monotonic()
    loading = wants_loading_motif(shot_type, visual_purpose)
    with Image.open(source_path) as img:
        img = img.convert("RGB")
        img = _poster_contrast(img)
        img = _vignette(img)
        img = draw_rect_border(img, _FRAME_COLOR, width=max(2, round(min(img.size) * 0.004)))
        img = _frame(img)
        if loading:
            img = _loading_motif(img)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, "JPEG", quality=92)
    return {
        "styleTreatment": "game_art",
        "layout": None,
        "loadingMotif": loading,
        "treatmentApplied": True,
        "processingTimeS": round(time.monotonic() - t0, 3),
    }
