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
BOTTOM_SAFE = 400
MIN_FONT_PX, MAX_FONT_PX = 64, 96
MIN_CONTRAST = 4.5
_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONTS = {"Poppins-Bold": _FONT_DIR / "Poppins-Bold.ttf"}


def _font(name: str, px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _FONTS.get(name)
    if path and path.is_file():
        return ImageFont.truetype(str(path), px)
    return ImageFont.load_default(size=px)


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


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def compose_card(image_path: str | Path, text: str, direction_id: str, out_path: str | Path) -> dict:
    """Illustration cover-cropped en 1080x1920 + voile + texte. Retourne un rapport de lisibilité mesuré."""
    spec = art_directions.get_direction(direction_id)["typography"]
    image = Image.open(image_path).convert("RGB")
    scale = max(W / image.width, H / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - W) // 2, (image.height - H) // 2
    card = image.crop((left, top, left + W, top + H))
    report = {"text": bool(text.strip()), "font_px": None, "lines": 0, "contrast": None, "fits": True}
    if text.strip():
        max_width = W - 2 * MARGIN_X
        probe = ImageDraw.Draw(card)
        font_px, lines = MAX_FONT_PX, []
        while font_px >= MIN_FONT_PX:
            font = _font(spec["font"], font_px)
            lines = wrap_lines(probe, text.strip(), font, max_width)
            if len(lines) <= 4:
                break
            font_px -= 4
        font_px = max(font_px, MIN_FONT_PX)
        font = _font(spec["font"], font_px)
        lines = wrap_lines(probe, text.strip(), font, max_width)
        line_h = round(font_px * 1.22)
        block_h = line_h * len(lines)
        bottom = H - BOTTOM_SAFE
        top_y = bottom - block_h
        report["fits"] = len(lines) <= 5 and top_y > H * 0.45
        # voile dégradé : transparent -> opaque à 78 % sous le texte
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        start = top_y - 220
        r, g, b = _hex(spec["scrim"])
        for y in range(max(start, 0), H):
            t = min(1.0, (y - start) / 220)
            sd.line([(0, y), (W, y)], fill=(r, g, b, round(200 * t)))
        card = Image.alpha_composite(card.convert("RGBA"), scrim).convert("RGB")
        draw = ImageDraw.Draw(card)
        for i, line in enumerate(lines):
            draw.text((MARGIN_X, top_y + i * line_h), line, font=font, fill=_hex(spec["text_color"]))
        # contraste mesuré : couleur moyenne de (illustration + voile) SOUS le bloc de texte, avant le texte
        base = Image.alpha_composite(image.crop((left, top, left + W, top + H)).convert("RGBA"), scrim).convert("RGB")
        bg = base.crop((MARGIN_X, top_y, W - MARGIN_X, bottom)).resize((1, 1), Image.BOX).getpixel((0, 0))
        report.update(font_px=font_px, lines=len(lines), contrast=round(contrast_ratio(_hex(spec["text_color"]), bg), 2))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    card.save(out_path, "JPEG", quality=92)
    return report
