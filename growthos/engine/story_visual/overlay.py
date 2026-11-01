"""Typographie composée localement (Pillow) sur l'illustration : jamais dessinée par le modèle d'image.

Zone sûre 1080x1920 : marges latérales 96 px, texte dans le bas du cadre mais au-dessus de l'interface des Shorts
(≈ 380 px en bas). Corps minimal 64 px (lisible sur téléphone). Un voile dégradé garantit un contraste mesuré.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import art_directions

W, H = 1080, 1920
MARGIN_X = 96
MARGIN_RIGHT = 168   # colonne d'actions des Shorts à droite
BOTTOM_SAFE = 440     # bandeau d'interface en bas (titre, compte, son)
MIN_FONT_PX, MAX_FONT_PX = 64, 96
MIN_CONTRAST = 4.5
MAX_INPUT_PIXELS = 36_000_000
_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONTS = {"Poppins-Bold": _FONT_DIR / "Poppins-Bold.ttf"}


def _font(name: str, px: int) -> ImageFont.FreeTypeFont:
    """Police du dépôt UNIQUEMENT : pas de repli silencieux (un rendu doit être identique d'une machine à l'autre)."""
    path = _FONTS.get(name)
    if not path or not path.is_file():
        raise FileNotFoundError(f"typography font {name!r} is missing from assets/fonts")
    return ImageFont.truetype(str(path), px)


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _luminance(rgb) -> float:
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _break_long(draw, words, font, max_width):
    """Un mot plus large que la zone est coupé par caractères : le texte ne déborde jamais du cadre."""
    for word in words:
        if draw.textlength(word, font=font) <= max_width:
            yield word
            continue
        piece = ""
        for char in word:
            if draw.textlength(piece + char, font=font) > max_width and piece:
                yield piece
                piece = ""
            piece += char
        if piece:
            yield piece


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in _break_long(draw, paragraph.split(), font, max_width):
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def compose_layers(image_path: str | Path, text: str, direction_id: str, card_path: str | Path,
                   layer_path: str | Path | None) -> dict:
    """Sépare l'IMAGE (carte 1080x1920 sans texte, JPEG) du TEXTE (calque RGBA : voile + légende, PNG, ou aucun fichier s'il n'y a pas de
    texte). Le rendu fait un fondu séquencé du texte (sortie puis entrée) pendant que les images se fondent : deux légendes ne se
    superposent jamais. Retourne un rapport de lisibilité mesuré (pire cas)."""
    spec = art_directions.get_direction(direction_id)["typography"]
    with Image.open(image_path) as probe:
        if probe.width * probe.height > MAX_INPUT_PIXELS or probe.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("illustration refused: unsupported format or too many pixels")
        image = probe.convert("RGB")
    scale = max(W / image.width, H / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - W) // 2, (image.height - H) // 2
    card = image.crop((left, top, left + W, top + H))
    report = {"text": bool(text.strip()), "font_px": None, "lines": 0, "contrast": None, "fits": True, "ok": True, "has_layer": False}
    layer = None
    if text.strip():
        max_width = W - MARGIN_X - MARGIN_RIGHT
        probe_draw = ImageDraw.Draw(card)
        font_px = MAX_FONT_PX
        while font_px >= MIN_FONT_PX:
            font = _font(spec["font"], font_px)
            lines = wrap_lines(probe_draw, text.strip(), font, max_width)
            if len(lines) <= 4:
                break
            font_px -= 4
        font_px = max(font_px, MIN_FONT_PX)
        font = _font(spec["font"], font_px)
        lines = wrap_lines(probe_draw, text.strip(), font, max_width)
        line_h = round(font_px * 1.22)
        bottom = H - BOTTOM_SAFE
        top_y = bottom - line_h * len(lines)
        report["fits"] = len(lines) <= 5 and top_y > H * 0.45
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # voile dégradé : transparent -> opaque à 78 % sous le texte
        sd = ImageDraw.Draw(layer)
        start = top_y - 220
        r, g, b = _hex(spec["scrim"])
        for y in range(max(start, 0), H):
            sd.line([(0, y), (W, y)], fill=(r, g, b, round(200 * min(1.0, (y - start) / 220))))
        base = Image.alpha_composite(card.convert("RGBA"), layer).convert("RGB")
        for i, line in enumerate(lines):
            sd.text((MARGIN_X, top_y + i * line_h), line, font=font, fill=_hex(spec["text_color"]) + (255,))
        # PIRE cas : contraste mesuré sur une grille de cellules sous le texte (illustration + voile, avant le texte)
        grid = base.crop((MARGIN_X, top_y, W - MARGIN_RIGHT, bottom)).resize((12, 4), Image.BOX)
        worst = min(contrast_ratio(_hex(spec["text_color"]), grid.getpixel((x, y))) for y in range(4) for x in range(12))
        report.update(font_px=font_px, lines=len(lines), contrast=round(worst, 2), has_layer=True)
    report["ok"] = bool(report["fits"]) and (report["contrast"] is None or report["contrast"] >= MIN_CONTRAST)
    Path(card_path).parent.mkdir(parents=True, exist_ok=True)
    card.save(card_path, "JPEG", quality=92)
    if layer is not None and layer_path is not None:
        layer.save(layer_path, "PNG")
    return report


def compose_card(image_path: str | Path, text: str, direction_id: str, out_path: str | Path) -> dict:
    """Carte complète (image + texte) en un seul JPEG : aperçu et tests. Le rendu vidéo utilise `compose_layers`."""
    out = Path(out_path)
    layer = out.with_suffix(".layer.png")
    report = compose_layers(image_path, text, direction_id, out, layer)
    if report["has_layer"]:
        with Image.open(out) as card, Image.open(layer) as top:
            Image.alpha_composite(card.convert("RGBA"), top).convert("RGB").save(out, "JPEG", quality=92)
    layer.unlink(missing_ok=True)
    return report
