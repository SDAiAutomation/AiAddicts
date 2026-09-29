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

from PIL import Image, ImageDraw, ImageFont

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


def sanitize_text(text: str) -> str:
    replaced = "".join(_CHAR_FALLBACK.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", replaced)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.encode("ascii", "ignore").decode("ascii")


@lru_cache(maxsize=None)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=max(1, size))


def safe_box(width: int, height: int) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the region outside caption/platform-UI zones."""
    return 0, round(height * SAFE_TOP_RATIO), width, round(height * (1 - SAFE_BOTTOM_RATIO))


def new_frame(size: tuple[int, int], background: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    from .theme import hex_to_rgb

    image = Image.new("RGB", size, hex_to_rgb(background))
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
    """`bold` fakes a heavier weight via stroke — Pillow's bundled default
    font only ships one weight."""
    stroke_width = max(1, f.size // 22) if bold else 0
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
    """Composites a soft translucent rounded panel at `box` onto `image` and
    returns the new `(image, draw)` pair — used for card-style groupings
    within a scene (e.g. each row of a money split, a comparison card)."""
    from .theme import hex_to_rgb

    if alpha <= 0:
        return image, ImageDraw.Draw(image)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius=max(0, radius), fill=(*hex_to_rgb(color), alpha))
    composited = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    return composited, ImageDraw.Draw(composited)
