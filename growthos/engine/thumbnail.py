"""Miniature YouTube (1280x720) d'un quiz long, en trois variantes à tester.

Rendu déterministe avec Pillow : aucun appel fournisseur, donc aucun coût et
aucun texte déformé par un modèle d'image. Règles appliquées (les chiffres
précis ne sont pas démontrés : ce sont des hypothèses à valider avec le test
A/B de YouTube, voir docs/thumbnails.md) :

- 1280x720 (16:9), JPEG sous les 2 Mo acceptés partout, y compris par l'API ;
- lisible à ~170 px de large (liste mobile) : peu d'éléments, très gros, avec
  contour ; tailles de police et contraste contrôlés (voir `check`) ;
- un point focal principal, fort contraste, couleurs du thème du quiz ;
- la promesse est le nombre réel de questions, jamais une statistique ni un
  résultat garanti ; un sujet qui contient une telle promesse est écarté ;
- le coin bas-droit reste vide : YouTube y pose la durée.

Variantes (jamais plus d'une idée change à la fois, pour que le test A/B
apprenne quelque chose) :
  A  sujet dominant + cartes de réponse (publiée automatiquement)
  B  nombre de questions dominant (le chiffre remplace les cartes)
  C  sujet dominant, sans cartes (texte plus grand)
"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Poppins-Bold.ttf"
MARGIN = 72
TEXT_WIDTH = 630  # colonne de texte quand des éléments occupent la droite

# Zone réservée à la durée affichée par YouTube : 20 % de la largeur sur 15 % de la hauteur.
# Les guides ne s'accordent pas sur la taille exacte (100x30 px à 20 %) : on prend la plus large.
SAFE_ZONE = (round(WIDTH * 0.80), round(HEIGHT * 0.85), WIDTH, HEIGHT)
# Plus petite taille de police (à 168 px de large, vignette « suggérées ») jugée lisible, en pixels.
MIN_FONT_AT_168 = 8
# Seuil WCAG des grands textes (>= 24 px gras) : tous les textes de la miniature font au moins 64 px.
MIN_CONTRAST = 3.0
MAX_BYTES = 2 * 1024 * 1024
MIN_TOPIC_FONT = 72

VARIANTS = {"A": "topic", "B": "number", "C": "text"}

# Libellé du nombre de questions, par langue du script.
_QUESTIONS_LABEL = {
    "fr": "QUESTIONS", "en": "QUESTIONS", "es": "PREGUNTAS",
    "de": "FRAGEN", "it": "DOMANDE", "pt": "PERGUNTAS",
}

# Mots qui ne terminent jamais proprement un titre raccourci.
_TRAILING_WORDS = {
    "DE", "DU", "DES", "LA", "LE", "LES", "L'", "D'", "ET", "OU", "AU", "AUX", "EN", "UN", "UNE",
    "SES", "SON", "SA", "SUR", "PAR", "POUR", "DANS", "AVEC", "SANS", "CE", "CET", "CES", "QUI", "QUE",
    "OF", "THE", "AND", "OR", "IN", "ON", "TO", "A", "AN", "FOR", "WITH", "HIS", "HER", "ITS", "THEIR",
    "FROM", "BY", "AT", "AS", "IS", "ARE",
    "EL", "LOS", "LAS", "Y", "UND", "DER", "DIE", "DAS", "DI", "IL", "E", "O", "OS", "AS", "DA", "DO",
}

# Promesses qu'une miniature ne doit jamais faire : statistique ou résultat non vérifiable.
_CLAIM = re.compile(r"%|impossible|garanti|guarantee|seulement\s+\d|only\s+\d|nobody|personne ne", re.IGNORECASE)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _luminance(colour: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _best_ink(background: tuple[int, int, int]) -> tuple[int, int, int]:
    dark, light = _rgb("#0f172a"), (255, 255, 255)
    return dark if contrast_ratio(dark, background) >= contrast_ratio(light, background) else light


def has_claim(text: str) -> bool:
    """Vrai si le texte promet une statistique ou un résultat (« 99 % échouent », « impossible »…)."""
    return bool(_CLAIM.search(text or ""))


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
               max_lines: int = 3, min_size: int = MIN_TOPIC_FONT, max_size: int = 190) -> tuple[int, list[str], bool]:
    """Plus grande taille qui tient en `max_lines` lignes dans la boîte.

    Si même `min_size` ne suffit pas, le sujet est raccourci au dernier mot
    entier (jamais sur un « de », « of »…) : mieux vaut un titre court lisible
    à 170 px qu'un titre complet illisible. Retourne (taille, lignes, raccourci)."""
    words = text.split()
    trimmed = False
    while words:
        candidate = " ".join(words)
        for size in range(max_size, min_size - 1, -6):
            lines = _wrap(draw, candidate, size, max_width)
            widest = max((draw.textlength(line, font=_font(size)) for line in lines), default=0)
            if len(lines) <= max_lines and widest <= max_width and len(lines) * size * 1.02 <= max_height:
                return size, lines, trimmed
        words.pop()
        while words and words[-1] in _TRAILING_WORDS:
            words.pop()
        trimmed = True
    return min_size, [], True


def _outlined(draw, xy, text, font, fill, outline, width=6, anchor="la"):
    draw.text(xy, text, font=font, fill=fill, stroke_width=width, stroke_fill=outline, anchor=anchor)


def _save_jpeg(image: Image.Image, out_path: str) -> int:
    """Enregistre en JPEG en baissant la qualité jusqu'à tenir sous la limite ; retourne la taille."""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    for quality in (88, 80, 72, 64, 56):
        image.save(out_path, "JPEG", quality=quality, optimize=True)
        size = Path(out_path).stat().st_size
        if size < MAX_BYTES * 0.9:
            return size
    raise ValueError("miniature trop lourde pour YouTube (2 Mo)")


def render_variant(topic: str | None, question_count: int, theme_colours: tuple[str, str, str, str],
                   language: str = "fr", variant: str = "A", out_path: str | None = None) -> tuple[Image.Image, dict]:
    """Retourne (image, rapport de contrôle). `theme_colours` = (fond, texte, bonne réponse, accent)."""
    if variant not in VARIANTS:
        raise ValueError(f"variante inconnue : {variant}")
    card_hex, text_hex, correct_hex, accent_hex = theme_colours
    background, ink = _rgb(card_hex), _rgb(text_hex)
    correct, accent = _rgb(correct_hex), _rgb(accent_hex)
    dark = background if sum(background) < 384 else _rgb("#0f172a")
    if sum(background) >= 384:
        # Thème clair : une miniature claire se fond dans la page YouTube ; on bascule sur un fond sombre.
        background, ink = dark, _rgb("#ffffff")
        if sum(accent) < 300:
            accent = _rgb("#facc15")
    # Un accent sombre ou saturé (bleu, violet) manque de contraste sur le fond sombre : on l'éclaircit.
    for step in range(16):
        if contrast_ratio(accent, background) >= MIN_CONTRAST + 0.6:
            break
        accent = _mix(accent, (255, 255, 255), 0.2)
    lighter = _mix(background, _rgb("#ffffff"), 0.12)

    def backdrop(x: float) -> tuple[int, int, int]:
        t = max(0.0, min(1.0, x / WIDTH))
        return _mix(background, lighter, t * t)

    image = Image.new("RGB", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    for x in range(WIDTH):
        draw.line([(x, 0), (x, HEIGHT)], fill=backdrop(x))
    draw.rectangle([0, 0, 18, HEIGHT], fill=accent)

    texts: list[tuple[str, int, tuple[int, int, int], tuple[int, int, int]]] = []  # (texte, taille, couleur, fond)
    issues: list[str] = []

    clean = " ".join(str(topic or "").upper().split())
    if clean.endswith(" QUIZ"):
        clean = clean[:-5].strip()
    if clean == "QUIZ":
        clean = ""
    if has_claim(clean):
        # Une promesse chiffrée ou « impossible » dans le sujet n'est jamais affichée.
        issues.append("topic_claim_removed")
        clean = ""

    number_text = str(question_count)
    label_text = f"{question_count} {_QUESTIONS_LABEL.get(language, 'QUESTIONS')}"
    topic_trimmed = False
    pill_ink = _best_ink(accent)

    def draw_cards() -> None:
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
                texts.append((letters[index], 88, accent, fill))

    def draw_pill() -> None:
        pill_font = _font(64)
        pill_w = round(draw.textlength(label_text, font=pill_font)) + 70
        pill = [MARGIN, HEIGHT - 60 - 100, MARGIN + pill_w, HEIGHT - 60]
        draw.rounded_rectangle(pill, radius=50, fill=accent)
        draw.text(((pill[0] + pill[2]) / 2, (pill[1] + pill[3]) / 2 + 2), label_text, font=pill_font,
                  fill=pill_ink, anchor="mm")
        texts.append((label_text, 64, pill_ink, accent))

    def draw_topic(max_width: int, max_height: int, max_lines: int, y: int) -> int:
        nonlocal topic_trimmed
        if not clean:
            return y
        size, lines, topic_trimmed = _fit_title(draw, clean, max_width, max_height, max_lines)
        font = _font(size)
        for line in lines:
            _outlined(draw, (MARGIN, y), line, font, ink, dark, width=max(4, size // 22))
            y += round(size * 1.02)
        if lines:
            texts.append((" ".join(lines), size, ink, backdrop(MARGIN + max_width / 2)))
        return y

    def draw_quiz_word(y: int, size: int = 150) -> int:
        if not clean:
            # Sans sujet affiché, « QUIZ » porte seul la miniature : plus grand et plus bas.
            y, size = 120, 270
        _outlined(draw, (MARGIN, y + 4), "QUIZ", _font(size), accent, dark, width=8)
        texts.append(("QUIZ", size, accent, backdrop(MARGIN + 200)))
        return y + round(size * 1.13)

    if variant == "A":
        y = draw_topic(TEXT_WIDTH, 300, 3, 60)
        draw_quiz_word(y)
        draw_pill()
        draw_cards()
    elif variant == "C":
        # Sans cartes : la colonne de texte occupe toute la largeur utile, donc un sujet plus grand.
        y = draw_topic(WIDTH - 2 * MARGIN, 330, 3, 60)
        draw_quiz_word(y, 170)
        draw_pill()
    else:
        # B : le nombre de questions devient le point focal, à droite, à la place des cartes.
        y = draw_topic(TEXT_WIDTH, 300, 3, 60)
        draw_quiz_word(y)
        number_font = _font(400)
        cx = WIDTH - MARGIN - 230
        _outlined(draw, (cx, 20), number_text, number_font, accent, dark, width=10, anchor="ma")
        texts.append((number_text, 400, accent, backdrop(cx)))
        word = _QUESTIONS_LABEL.get(language, "QUESTIONS")
        _outlined(draw, (cx, 470), word, _font(64), ink, dark, width=6, anchor="ma")
        texts.append((word, 64, ink, backdrop(cx)))

    # Contrôles automatiques (à 168 px de large, comme la vignette « suggérées »).
    scale = 168 / WIDTH
    smallest = min((size for _, size, _, _ in texts), default=0) * scale
    contrast = min((contrast_ratio(fill, bg) for _, _, fill, bg in texts), default=21.0)
    if smallest < MIN_FONT_AT_168:
        issues.append("font_too_small_at_168px")
    if contrast < MIN_CONTRAST:
        issues.append("low_contrast")
    zone = image.crop(SAFE_ZONE)
    safe_clear = all(
        max(abs(a - b) for a, b in zip(zone.getpixel((x, y)), backdrop(SAFE_ZONE[0] + x))) <= 12
        for x in range(0, zone.width, 8) for y in range(0, zone.height, 8)
    )
    if not safe_clear:
        issues.append("duration_badge_zone_not_empty")
    if topic_trimmed:
        issues.append("topic_shortened")

    report = {
        "variant": variant, "axis": VARIANTS[variant], "questionCount": question_count,
        "minFontPxAt168": round(smallest, 1), "minContrast": round(contrast, 1),
        "safeZoneClear": safe_clear, "topicShortened": topic_trimmed, "issues": issues,
    }
    if out_path:
        report["bytes"] = _save_jpeg(image, out_path)
    return image, report


def render_thumbnail(topic: str, question_count: int, theme_colours: tuple[str, str, str, str],
                     language: str = "fr", out_path: str | None = None) -> Image.Image:
    """Variante A (compatibilité) ; voir `render_variant`."""
    return render_variant(topic, question_count, theme_colours, language, "A", out_path)[0]


def is_long_quiz(script: dict) -> bool:
    return script.get("content_format") == "quiz" and (script.get("quiz") or {}).get("recipe") == "long"


def _script_parts(script: dict) -> tuple[str, int, tuple[str, str, str, str], str]:
    if not is_long_quiz(script):
        raise ValueError("miniature réservée aux quiz longs")
    from .captions import _QUIZ_THEME_COLOURS

    quiz = script["quiz"]
    colours = _QUIZ_THEME_COLOURS.get(quiz.get("theme"), _QUIZ_THEME_COLOURS["studio"])
    topic = quiz.get("topic") or (quiz.get("cover") or {}).get("title") or script.get("title") or "QUIZ"
    return str(topic), len(quiz.get("questions") or []), colours, str(script.get("language") or "fr")


def build_for_script(script: dict, out_path: str) -> str:
    """Miniature (variante A) d'un script quiz long ; lève si le script n'est pas un quiz long."""
    topic, count, colours, language = _script_parts(script)
    render_variant(topic, count, colours, language, "A", out_path)
    return out_path


def build_variants_for_script(script: dict, out_dir: str) -> dict[str, dict]:
    """Les trois variantes d'un quiz long : {"A": {"path", "axis", "report"}, ...}.

    La variante A est celle envoyée automatiquement à YouTube ; B et C sont
    à téléverser à la main dans « Test & Compare » (jamais d'API pour le test)."""
    topic, count, colours, language = _script_parts(script)
    results: dict[str, dict] = {}
    for variant in VARIANTS:
        path = str(Path(out_dir) / f"thumbnail-{variant.lower()}.jpg")
        _, report = render_variant(topic, count, colours, language, variant, path)
        results[variant] = {"path": path, "axis": VARIANTS[variant], "report": report}
    return results
