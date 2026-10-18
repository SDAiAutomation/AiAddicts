"""Miniature YouTube (1280x720) d'un quiz long.

Rendu déterministe avec Pillow : aucun appel fournisseur, donc aucun coût et
aucun texte déformé par un modèle d'image. Règles appliquées, celles qui
fonctionnent sur YouTube :

- 1280x720 (16:9), JPEG bien sous les 2 Mo acceptés par l'API ;
- lisible en ~170 px de large (liste mobile) : peu de mots, très gros, contour ;
- un seul point focal, fort contraste, couleurs du thème du quiz ;
- le nombre de questions est la promesse concrète, jamais une statistique ni un
  résultat garanti ;
- le coin bas-droit reste vide : YouTube y pose la durée.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Poppins-Bold.ttf"
MARGIN = 72
TEXT_WIDTH = 630  # colonne de texte ; le reste est le décor « cartes de réponse »

# Libellé du nombre de questions, par langue du script.
_QUESTIONS_LABEL = {
    "fr": "QUESTIONS", "en": "QUESTIONS", "es": "PREGUNTAS",
    "de": "FRAGEN", "it": "DOMANDE", "pt": "PERGUNTAS",
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _wrap(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    font = _font(size)
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_title(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int,
               max_lines: int = 3) -> tuple[int, list[str]]:
    """Plus grande taille qui tient en `max_lines` lignes dans la boîte."""
    for size in range(190, 59, -6):
        lines = _wrap(draw, text, size, max_width)
        widest = max((draw.textlength(line, font=_font(size)) for line in lines), default=0)
        if len(lines) <= max_lines and widest <= max_width and len(lines) * size * 1.02 <= max_height:
            return size, lines
    size = 60
    return size, _wrap(draw, text, size, max_width)[:max_lines]


def _outlined(draw, xy, text, font, fill, outline, width=6, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, stroke_width=width, stroke_fill=outline, anchor=anchor)


def render_thumbnail(topic: str, question_count: int, theme_colours: tuple[str, str, str, str],
                     language: str = "fr", out_path: str | None = None) -> Image.Image:
    """`theme_colours` = (fond, texte, bonne réponse, accent), comme les thèmes de quiz."""
    card_hex, text_hex, correct_hex, accent_hex = theme_colours
    background, ink = _rgb(card_hex), _rgb(text_hex)
    correct, accent = _rgb(correct_hex), _rgb(accent_hex)
    dark = background if sum(background) < 384 else _rgb("#0f172a")
    if sum(background) >= 384:
        # Thème clair : une miniature claire se fond dans la page YouTube ; on bascule sur un fond sombre.
        background, ink = dark, _rgb("#ffffff")
        if sum(accent) < 300:
            accent = _rgb("#facc15")

    image = Image.new("RGB", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    # Dégradé diagonal discret : de la profondeur sans bruit visuel.
    lighter = _mix(background, _rgb("#ffffff"), 0.12)
    for x in range(WIDTH):
        t = x / WIDTH
        draw.line([(x, 0), (x, HEIGHT)], fill=_mix(background, lighter, t * t))
    draw.rectangle([0, 0, 18, HEIGHT], fill=accent)

    # Colonne de texte : sujet (très gros), « QUIZ » en accent, pastille du nombre de questions.
    topic = " ".join(str(topic or "").upper().split()) or "QUIZ"
    if topic.endswith(" QUIZ"):
        topic = topic[:-5].strip() or topic
    top = 60
    size, lines = _fit_title(draw, topic, TEXT_WIDTH, 300)
    y = top
    font = _font(size)
    for line in lines:
        _outlined(draw, (MARGIN, y), line, font, ink, dark, width=max(4, size // 22))
        y += round(size * 1.02)
    quiz_font = _font(150)
    _outlined(draw, (MARGIN, y + 4), "QUIZ", quiz_font, accent, dark, width=8)
    y += 170

    label = f"{question_count} {_QUESTIONS_LABEL.get(language, 'QUESTIONS')}"
    pill_font = _font(58)
    pill_w = round(draw.textlength(label, font=pill_font)) + 70
    pill = [MARGIN, HEIGHT - 60 - 92, MARGIN + pill_w, HEIGHT - 60]
    draw.rounded_rectangle(pill, radius=46, fill=accent)
    pill_ink = _rgb("#0f172a") if sum(accent) > 380 else _rgb("#ffffff")
    draw.text(((pill[0] + pill[2]) / 2, (pill[1] + pill[3]) / 2 + 2), label, font=pill_font,
              fill=pill_ink, anchor="mm")

    # Décor : quatre cartes de réponse, comme dans la vidéo, dont une validée.
    card_w, card_h, gap = 200, 140, 24
    origin_x = WIDTH - MARGIN - (2 * card_w + gap)
    origin_y = 140
    letters = "ABCD"
    for index in range(4):
        col, row = index % 2, index // 2
        x0 = origin_x + col * (card_w + gap)
        y0 = origin_y + row * (card_h + gap)
        selected = index == 2
        fill = correct if selected else _mix(background, _rgb("#ffffff"), 0.12)
        draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=26, fill=fill,
                               outline=ink if selected else None, width=5)
        cx, cy = x0 + card_w / 2, y0 + card_h / 2
        if selected:
            # Coche dessinée : la police n'a pas de glyphe ✓.
            draw.line([(cx - 36, cy + 2), (cx - 10, cy + 30), (cx + 40, cy - 30)],
                      fill=(255, 255, 255), width=20, joint="curve")
        else:
            draw.text((cx, cy), letters[index], font=_font(88), fill=accent, anchor="mm")
    # Un point d'interrogation géant derrière les cartes appelle la curiosité sans rien révéler.
    draw.text((origin_x + card_w + gap / 2, origin_y + card_h * 2 + gap + 120), "?", font=_font(190),
              fill=accent, anchor="mm", stroke_width=6, stroke_fill=dark)

    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        image.save(out_path, "JPEG", quality=88, optimize=True)
    return image


def is_long_quiz(script: dict) -> bool:
    return script.get("content_format") == "quiz" and (script.get("quiz") or {}).get("recipe") == "long"


def build_for_script(script: dict, out_path: str) -> str:
    """Miniature d'un script quiz long ; lève si le script n'est pas un quiz long."""
    if not is_long_quiz(script):
        raise ValueError("miniature réservée aux quiz longs")
    from .captions import _QUIZ_THEME_COLOURS

    quiz = script["quiz"]
    colours = _QUIZ_THEME_COLOURS.get(quiz.get("theme"), _QUIZ_THEME_COLOURS["studio"])
    topic = quiz.get("topic") or (quiz.get("cover") or {}).get("title") or script.get("title") or "QUIZ"
    count = len(quiz.get("questions") or [])
    render_thumbnail(str(topic), count, colours, str(script.get("language") or "fr"), out_path)
    return out_path
