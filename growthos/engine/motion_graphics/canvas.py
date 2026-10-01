"""Low-level drawing helpers shared by every motion-graphics scene.

Text uses Pillow's own bundled scalable default font (`ImageFont.load_default
(size=...)`, available since Pillow 10.1) rather than a font file this repo
would have to ship and keep in sync across the dev machine and the render
worker — see engine/video.py's own font-availability caveat for `.srt`
captions (`SUBTITLE_FONT`), which this sidesteps entirely.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Bundled Poppins (SIL OFL, assets/fonts/OFL.txt): real regular + bold weights
# and full Latin accents, so scripts in fr/es/de/it/pt render correctly. If the
# files are ever missing we fall back to Pillow's ASCII-only default font.
_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONT_FILES = {False: _FONT_DIR / "Poppins-Regular.ttf", True: _FONT_DIR / "Poppins-Bold.ttf"}
_BUNDLED_FONTS = all(path.is_file() for path in _FONT_FILES.values())

# SAFE_TOP_RATIO mirrors the platform-UI band (profile/follow button) —
# unaffected by Phase 2.7, unchanged from the original estimate.
#
# SAFE_BOTTOM_RATIO (Phase 2.7) is DERIVED from engine/captions.py's real
# caption-rendering constants, not chosen:
#   - tallest caption style: word_pop, font_size=104px (_CAPTION_STYLES)
#   - largest margin_v across styles: 550px (sleek/boxed; word_pop uses 540)
#   - a caption cue CAN wrap to 2 lines (WrapStyle=0 in the .ass header;
#     _MAX_CUE_CHARS=22 only shrinks the font past that length, it does not
#     guarantee a single line)
#   - ~1.2x font size per rendered line is the standard ascent+descent+
#     leading approximation for a sans-serif face at Spacing=0
#   reserved_px = margin_v + 2 * font_size * 1.2
#               = 550 + 2 * 104 * 1.2 = 799.6px on a 1920-tall reference canvas
#   reserved_ratio = 799.6 / 1920 ≈ 0.4165, rounded to 0.42
# Was 0.30 (a single-caption-line budget) before Phase 2.7's layout audit —
# see engine/motion_graphics/layout.py and the Phase 2.7 report for the
# collision this under-sizing allowed.
SAFE_TOP_RATIO = 0.09
SAFE_BOTTOM_RATIO = 0.42

# Verified empirically (rendered + inspected a real frame): Pillow's bundled
# default font (Aileron, via ImageFont.load_default) only covers basic ASCII —
# accented Latin letters, em/en dashes and the true minus sign all come out
# as a missing-glyph box. Faceloop scripts can be fr/es/de/it/pt, so this
# replaces what it can before falling back to dropping anything left.
# The burned narration captions (engine/captions.py, libass + system fonts)
# are unaffected and keep full accents.
_CHAR_FALLBACK = {
    "−": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
    "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
    "ß": "ss", "ø": "o", "Ø": "O",
}


def _keeps_glyph(ch: str) -> bool:
    code = ord(ch)
    return code < 0x250 or 0x2010 <= code <= 0x2027 or 0x20A0 <= code <= 0x20BF


def sanitize_text(text: str) -> str:
    if _BUNDLED_FONTS:
        # Poppins covers Latin + Latin Extended and common punctuation; drop
        # only what it cannot draw (emoji, CJK...) and map the true minus sign.
        replaced = text.replace("\u2212", "-")
        return unicodedata.normalize("NFC", "".join(ch for ch in replaced if _keeps_glyph(ch)))
    replaced = "".join(_CHAR_FALLBACK.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", replaced)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.encode("ascii", "ignore").decode("ascii")


@lru_cache(maxsize=None)
def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    if _BUNDLED_FONTS:
        return ImageFont.truetype(str(_FONT_FILES[bool(bold)]), max(1, size))
    return ImageFont.load_default(size=max(1, size))


def faux_bold_stroke(font_px: int, bold: bool) -> int:
    """Stroke width used to fake a heavier weight - only needed on the
    single-weight default-font fallback; the bundled Bold is a real weight."""
    return 0 if _BUNDLED_FONTS or not bold else max(1, font_px // 22)


def safe_box(width: int, height: int) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the region outside caption/platform-UI zones."""
    return 0, round(height * SAFE_TOP_RATIO), width, round(height * (1 - SAFE_BOTTOM_RATIO))


@lru_cache(maxsize=8)
def _backdrop(size: tuple[int, int], background: str, glow: str) -> Image.Image:
    """Soft radial backdrop: a gentle lift of the theme colour towards the
    upper third, a faint tint of `glow` behind the content, darker corners.
    Computed on a small grid and upscaled bicubic, so it is smooth and cheap."""
    from .theme import hex_to_rgb

    width, height = size
    gw, gh = 48, max(2, round(48 * height / width))
    base, tint = hex_to_rgb(background), hex_to_rgb(glow)
    small = Image.new("RGB", (gw, gh))
    px = small.load()
    for y in range(gh):
        for x in range(gw):
            nx, ny = (x + 0.5) / gw, (y + 0.5) / gh
            d_top = ((nx - 0.5) ** 2 + ((ny - 0.30) * 0.75) ** 2) ** 0.5
            lift = max(0.0, 1.0 - d_top / 0.75) * 0.10
            glow_k = max(0.0, 1.0 - (((nx - 0.5) ** 2 + (ny - 0.46) ** 2) ** 0.5) / 0.45) * 0.07
            edge = max(0.0, (((nx - 0.5) ** 2 + (ny - 0.5) ** 2) ** 0.5 - 0.35) / 0.45) * 0.28
            px[x, y] = tuple(
                max(0, min(255, round((base[i] + (255 - base[i]) * lift) * (1 - edge) * (1 - glow_k) + tint[i] * glow_k)))
                for i in range(3)
            )
    return small.resize(size, Image.BICUBIC)


def new_frame(size: tuple[int, int], background: str, glow: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = _backdrop(tuple(size), background, glow or background).copy()
    return image, ImageDraw.Draw(image)


def text_size(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, stroke_width: int = 0) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), sanitize_text(text), font=f, stroke_width=stroke_width)
    return right - left, bottom - top


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    f: ImageFont.FreeTypeFont,
    fill,
    anchor: str = "mm",
    bold: bool = False,
) -> None:
    """`bold` only fakes a heavier weight (stroke) on the default-font fallback."""
    stroke_width = faux_bold_stroke(f.size, bold)
    draw.text(xy, sanitize_text(text), font=f, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=fill)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    text = sanitize_text(text)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if not current or text_size(draw, trial, f)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius: float, fill=None, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=max(0, radius), fill=fill, outline=outline, width=width)


def panel(image: Image.Image, box, radius: float, color: str, alpha: int = 26) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Composites a translucent "glass" card at `box` onto `image`: soft drop
    shadow, tinted fill, fine light border. Works on a cropped region only
    (the blur is the expensive part) and updates `image` in place. Returns
    `(image, draw)` - used for card-style groupings within a scene."""
    from .theme import hex_to_rgb

    if alpha <= 0:
        return image, ImageDraw.Draw(image)
    x0, y0, x1, y1 = (round(v) for v in box)
    blur = max(4, round(image.size[0] * 0.012))
    drop = round(blur * 0.8)
    margin = blur * 3
    left, top = max(0, x0 - margin), max(0, y0 - margin)
    right, bottom = min(image.size[0], x1 + margin), min(image.size[1], y1 + margin + drop)
    if right <= left or bottom <= top:
        return image, ImageDraw.Draw(image)
    region = image.crop((left, top, right, bottom)).convert("RGBA")
    local = (x0 - left, y0 - top, x1 - left, y1 - top)

    shadow = Image.new("RGBA", region.size, (0, 0, 0, 0))
    shadow_alpha = min(110, round(alpha * 3.2))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (local[0], local[1] + drop, local[2], local[3] + drop), radius=max(0, radius), fill=(0, 0, 0, shadow_alpha))
    region = Image.alpha_composite(region, shadow.filter(ImageFilter.GaussianBlur(blur)))

    card = Image.new("RGBA", region.size, (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle(
        local, radius=max(0, radius), fill=(*hex_to_rgb(color), min(255, round(alpha * 1.25))),
        outline=(255, 255, 255, min(70, round(alpha * 1.8))), width=max(1, round(image.size[0] / 540)))
    region = Image.alpha_composite(region, card).convert("RGB")
    image.paste(region, (left, top))
    return image, ImageDraw.Draw(image)
