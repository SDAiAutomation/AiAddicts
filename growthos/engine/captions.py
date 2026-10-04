"""Build caption files (SRT + ASS) from per-word timing.

Sous-titres animés : au lieu d'un bloc entier affiché d'un coup pendant
toute sa durée, chaque cue ne montre que quelques mots, enchaînés au débit
réel de la voix (timing ElevenLabs, voir engine/tts.synthesize_with_timestamps)
— look "CapCut/Reels" standard plutôt qu'un pavé de texte statique.

Le style visuel des sous-titres (`caption_style` du script) est porté par le
fichier `.ass` (`write_ass`) : libass sait tout faire (contour épais, boîte
opaque, halo coloré, surlignage du mot en cours). `write_srt` reste écrit en
parallèle pour le debug / repli.
"""
import os
import textwrap
from pathlib import Path

# 2-4 mots par écran (choisi avec l'utilisateur) : assez court pour bouger
# vite, assez long pour rester lisible.
_WORDS_PER_CUE = 3

DEFAULT_CAPTION_STYLE = "bold_stroke"

# Pas de sous-titres incrustés : seule la narration disparaît. Les cartes d'un
# quiz vivent dans le même .ass et restent dessinées. L'export .srt par version
# est écrit à part et n'est pas touché.
CAPTIONS_OFF = "off"

# Zone de sécurité TikTok/Reels/Shorts : l'interface recouvre environ les
# 320-500 px du bas d'un cadre 1920 (description, compte, musique) — bande
# commune sûre = 12 % à 72 % de la hauteur. Les sous-titres se posent donc avec
# ~540 px de marge basse : le bord bas du texte tombe sous 72 % de la hauteur,
# même sur deux lignes.
# Couleurs ASS = &HAABBGGRR (alpha inversé : 00 = opaque). Tailles en pixels
# (PlayResX/Y = résolution vidéo réelle, cf. write_ass). MarginV pensé pour
# un cadre 1920 de haut, mis à l'échelle par libass pour les autres formats.
_CAPTION_STYLES: dict[str, dict] = {
    # Gros blanc gras, contour noir épais — le défaut, lisible sur tout fond.
    "bold_stroke": {
        "font_size": 90, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": -1, "border_style": 1, "outline_w": 7,
        "shadow": 0, "spacing": 0, "margin_v": 540,
        "single_word": True,
    },
    # Plus fin, plus petit, interligne aéré, ombre douce — sobre.
    "sleek": {
        "font_size": 80, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": 0, "border_style": 1, "outline_w": 3,
        "shadow": 4, "spacing": 3, "margin_v": 550,
    },
    # Texte blanc sur bandeau noir semi-opaque (BorderStyle=3 = boîte).
    "boxed": {
        "font_size": 76, "primary": "&H00FFFFFF", "outline": "&HB3000000",
        "back": "&HB3000000", "bold": -1, "border_style": 3, "outline_w": 30,
        "shadow": 0, "spacing": 0, "margin_v": 550,
    },
    # Blanc + halo bleu accent (contour coloré + ombre portée colorée).
    "neon": {
        "font_size": 96, "primary": "&H00FFFFFF", "outline": "&H00EB6325",
        "back": "&H00EB6325", "bold": -1, "border_style": 1, "outline_w": 5,
        "shadow": 7, "spacing": 1, "margin_v": 540,
    },
    # Le mot en cours passe en jaune et grossit (look "MrBeast/Hormozi").
    "word_pop": {
        "font_size": 104, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": -1, "border_style": 1, "outline_w": 7,
        "shadow": 0, "spacing": 0, "margin_v": 540,
        "word_highlight": True, "highlight_colour": "&H0000D7FF&",  # or/jaune (override inline)
    },
}


def caption_style_or_default(name: str | None) -> str:
    return name if name in _CAPTION_STYLES or name == CAPTIONS_OFF else DEFAULT_CAPTION_STYLE


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_cues(
    block_words: list[tuple[list[dict], float]],
    gap: float = 0.15,
    block_roles: list[str] | None = None,
) -> list[dict]:
    """`block_words` : une entrée par bloc, dans l'ordre de lecture —
    (mots du bloc [{"text","start","end"} relatifs au bloc], durée réelle
    du bloc en secondes, mesurée par ffprobe). La durée réelle (pas juste
    la fin du dernier mot) sert à décaler les blocs suivants, pour rester
    calé sur l'audio concaténé (video.concat_audio ne met aucun blanc entre
    blocs — un décalage ici dériverait de bloc en bloc).

    Regroupe les mots par paquets de `_WORDS_PER_CUE`, ou deux mots pour les
    blocs `hook` afin d'accélérer le rythme visuel des premières secondes.

    Construit d'abord les bornes brutes de chaque groupe, puis leur applique
    la marge `gap` en une deuxième passe, bornée par le début du groupe
    *suivant* (bloc suivant compris) — sinon la marge d'un groupe peut
    déborder sur le début du suivant quand les mots s'enchaînent vite,
    produisant des cues qui se chevauchent dans le SRT."""
    raw: list[list] = []  # [start, end, text, words], sans la marge
    cursor = 0.0
    for block_index, (words, block_duration) in enumerate(block_words):
        role = block_roles[block_index] if block_roles and block_index < len(block_roles) else ""
        words_per_cue = 2 if role == "hook" else _WORDS_PER_CUE
        for start in range(0, len(words), words_per_cue):
            chunk = words[start:start + words_per_cue]
            text = " ".join(w["text"] for w in chunk)
            # Mots avec timing absolu (décalé du curseur bloc) — sert au
            # surlignage mot par mot des styles type "word_pop".
            abs_words = [
                {"text": w["text"], "start": cursor + w["start"], "end": cursor + w["end"]}
                for w in chunk
            ]
            raw.append([cursor + chunk[0]["start"], cursor + chunk[-1]["end"], text, abs_words, role])
        cursor += block_duration
    total_duration = cursor

    cues = []
    for i, (start, end, text, abs_words, role) in enumerate(raw):
        next_start = raw[i + 1][0] if i + 1 < len(raw) else total_duration
        cue_end = min(end + gap, next_start)
        cues.append({
            "index": i + 1, "start": start, "end": max(cue_end, start + 0.1),
            "text": text, "words": abs_words, "role": role,
        })
    return cues


def _ass_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    cs_total = round(seconds * 100)
    hours, cs_total = divmod(cs_total, 360_000)
    minutes, cs_total = divmod(cs_total, 6_000)
    secs, cs = divmod(cs_total, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    # `{` `}` délimitent les balises d'override ASS — neutralisés ; retours à
    # la ligne -> \N littéral.
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


# Un cue tient normalement en une ligne de ≤3 mots. Au-delà de ce nombre de
# caractères (mot très long, ou 3 mots longs), on réduit la police de ce cue
# pour qu'il ne déborde pas horizontalement du cadre — libass ne coupe jamais
# un mot, et WrapStyle 0 ne sauve que les lignes, pas les mots.
_MAX_CUE_CHARS = 22
_SHRINK_FACTOR = 0.78


def _cue_font_size(text: str, base_font_size: int) -> int:
    """Police (px) pour ce cue : `base_font_size`, réduite si le texte est long."""
    if len(text) <= _MAX_CUE_CHARS:
        return base_font_size
    return max(round(base_font_size * _SHRINK_FACTOR), round(base_font_size * 0.5))


def _ass_rgb(hex_rgb: str, alpha: int = 0) -> str:
    """"#rrggbb" (+ alpha ASS : 0 = opaque) -> "&HAABBGGRR"."""
    h = hex_rgb.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


# (fond des cartes, texte, fond de la bonne réponse, couleur du minuteur).
# Avec BorderStyle=3, libass dessine la carte avec OutlineColour : c'est donc le
# fond du thème qui doit y passer (avant, la carte restait noire et les thèmes
# clairs affichaient du texte sombre sur fond noir, illisible). Doit rester
# aligné avec QUIZ_THEMES de growthos-web (quiz-wizard.tsx).
_QUIZ_THEME_COLOURS = {
    "studio": ("#0f172a", "#ffffff", "#16a34a", "#facc15"),
    "arcade": ("#18102f", "#facc15", "#22c55e", "#ec4899"),
    "education": ("#3d2b1f", "#ffffff", "#16a34a", "#f59e0b"),
    "sport": ("#171717", "#ffffff", "#16a34a", "#22c55e"),
    "pop": ("#6a214e", "#ffffff", "#16a34a", "#fde047"),
    "minimal": ("#ffffff", "#111827", "#16a34a", "#111827"),
    "photo": ("#111827", "#ffffff", "#16a34a", "#0ea5e9"),
    "logo": ("#ffffff", "#111827", "#16a34a", "#2563eb"),
}
_QUIZ_CARD_ALPHA = 0x1F  # carte ~88 % opaque : le fond reste devinable sans nuire à la lecture

# Positions verticales (fraction de la hauteur) : tout reste dans la bande sûre 12-72 %.
_QUIZ_QUESTION_MARGIN_TOP = 250   # px sur 1920 (~13 %)


def _ass_header(width: int, height: int, preset: dict, font: str, quiz_theme: str = "studio") -> str:
    card_hex, text_hex, correct_hex, timer_hex = _QUIZ_THEME_COLOURS.get(quiz_theme, _QUIZ_THEME_COLOURS["studio"])
    quiz_text = _ass_rgb(text_hex)
    quiz_card = _ass_rgb(card_hex, _QUIZ_CARD_ALPHA)
    quiz_correct = _ass_rgb(correct_hex)
    quiz_accent = _ass_rgb(timer_hex)
    style_fields = ",".join(str(v) for v in [
        "Default", font, preset["font_size"],
        preset["primary"], preset["primary"], preset["outline"], preset["back"],
        preset["bold"], 0, 0, 0,            # Italic, Underline, StrikeOut
        100, 100, preset["spacing"], 0,     # ScaleX, ScaleY, Spacing, Angle
        preset["border_style"], preset["outline_w"], preset["shadow"],
        2, 60, 60, preset["margin_v"], 1,   # Alignment(bottom-center), margins, Encoding
    ])
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        # WrapStyle 0 = wrapping "intelligent" (lignes ~équilibrées, centrées via
        # Alignment=2) : un cue trop large passe sur 2 lignes au lieu d'être rogné.
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: {style_fields}\n"
        f"Style: QuizQuestion,{font},64,{quiz_text},{quiz_text},{quiz_card},{quiz_card},-1,0,0,0,100,100,0,0,3,24,0,8,80,80,{_QUIZ_QUESTION_MARGIN_TOP},1\n"
        f"Style: QuizChoice,{font},58,{quiz_text},{quiz_text},{quiz_card},{quiz_card},-1,0,0,0,100,100,0,0,3,20,0,5,100,100,0,1\n"
        f"Style: QuizCorrect,{font},64,&H00FFFFFF,&H00FFFFFF,{quiz_correct},{quiz_correct},-1,0,0,0,100,100,0,0,3,24,0,5,100,100,0,1\n"
        f"Style: QuizTimer,{font},180,{quiz_accent},{quiz_accent},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,0,5,0,0,0,1\n\n"
        f"Style: QuizPanel,{font},20,&H00FFFFFF,&H00FFFFFF,&HFF000000,&HFF000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
        f"Style: QuizCoverTitle,{font},128,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,3,28,0,5,90,90,0,1\n"
        f"Style: QuizCoverBrand,{font},40,{quiz_accent},{quiz_accent},&H00000000,&H00000000,-1,0,0,0,100,100,2,0,1,3,0,8,80,80,100,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _dialogue(start: float, end: float, text: str, style: str = "Default", layer: int = 0) -> str:
    return f"Dialogue: {layer},{_ass_timestamp(start)},{_ass_timestamp(end)},{style},,0,0,0,,{text}"


def _quiz_events(blocks: list[dict], durations: list[float], width: int, height: int) -> list[str]:
    """Cartes quiz calées sur les blocs compilés, avec timer pendant le silence final."""
    events: list[str] = []
    cursor = 0.0
    letters = "ABCD"
    for block, duration in zip(blocks, durations):
        start, end = cursor, cursor + max(float(duration), 0.0)
        phase = block.get("quiz_phase")
        if phase == "cover":
            title = _ass_escape(str(block.get("quiz_cover_title") or "QUIZ"))
            brand = _ass_escape(str(block.get("quiz_cover_brand") or "BrainLoop"))
            events.append(_dialogue(start, end, f"{{\\pos({width // 2},{round(height * 0.38)})\\fad(80,100)}}{title}", "QuizCoverTitle", 2))
            events.append(_dialogue(start, end, f"{{\\fad(80,100)}}{brand}", "QuizCoverBrand", 2))
            cursor = end
            continue
        if phase in {"question", "reveal"}:
            card, foreground, correct_colour, accent = _QUIZ_THEME_COLOURS.get(
                str(block.get("quiz_theme")), _QUIZ_THEME_COLOURS["studio"]
            )
            scale = min(width / 1080, height / 1920)
            # Symmetric margins keep every block centred on the screen. Stable
            # rows let the viewer locate their choice again when the answer appears.
            left, right = round(width * 0.08), round(width * 0.92)
            centre = width // 2
            card_width = right - left
            number = int(block.get("quiz_question_number") or 0)
            total = int(block.get("quiz_question_total") or 0)
            if number and total:
                badge_w = round(card_width * 0.12)
                events.append(_quiz_panel(start, end, left, round(height * 0.105), badge_w,
                                          round(height * 0.052), accent, scale))
                badge = f"{{\\an5\\pos({left + badge_w // 2},{round(height * 0.131)})\\fs{round(40 * scale)}\\bord0\\shad0\\1c{_ass_rgb(_contrast_text(accent))}}}{number}"
                events.append(_dialogue(start, end, badge, "QuizQuestion", 2))
                progress_x = left + badge_w + round(16 * scale)
                progress_w = right - progress_x
                label = f"{{\\an5\\pos({progress_x + progress_w // 2},{round(height * 0.119)})\\fs{round(28 * scale)}\\bord0\\shad0\\1c{_ass_rgb(accent)}}}QUESTION {number}/{total}"
                events.append(_dialogue(start, end, label, "QuizQuestion", 2))
                progress_y, progress_h = round(height * 0.144), max(3, round(8 * scale))
                events.append(_quiz_panel(start, end, progress_x, progress_y, progress_w, progress_h, card, scale))
                events.append(_quiz_panel(start, end, progress_x, progress_y,
                                          round(progress_w * min(number / total, 1)), progress_h, accent, scale))

            question_size, question = _quiz_fit_text(str(block.get("quiz_question") or ""),
                                                     card_width - round(64 * scale), round(72 * scale), 3)
            question_colour = accent
            events.append(_quiz_panel(start, end, left, round(height * 0.165), card_width,
                                      round(height * 0.105), question_colour, scale))
            question_tags = f"{{\\an5\\pos({centre},{round(height * 0.2175)})\\fs{question_size}\\bord0\\shad0\\1c{_ass_rgb(_contrast_text(question_colour))}\\q2}}"
            events.append(_dialogue(start, end, question_tags + question, "QuizQuestion", 2))

            has_visual = block.get("quiz_visual_available", True)
            if has_visual:
                # The generated visual remains visible through this window.
                # Four thin panels form a frame without covering the image.
                frame_y, frame_h = round(height * 0.285), round(height * 0.19)
                frame_t = max(3, round(7 * scale))
                # Spotlight: dim everything except the window so the picture
                # reads as a deliberate frame even when the image is soft.
                bleed = 60
                events.extend([
                    _quiz_scrim(start, end, -bleed, -bleed, width + 2 * bleed, frame_y + bleed, _QUIZ_SCRIM_ALPHA),
                    _quiz_scrim(start, end, -bleed, frame_y + frame_h, width + 2 * bleed,
                                height - frame_y - frame_h + bleed, _QUIZ_SCRIM_ALPHA),
                    _quiz_scrim(start, end, -bleed, frame_y, left + bleed, frame_h, _QUIZ_SCRIM_ALPHA),
                    _quiz_scrim(start, end, right, frame_y, width - right + bleed, frame_h, _QUIZ_SCRIM_ALPHA),
                ])
                events.extend([
                    _quiz_panel(start, end, left, frame_y, card_width, frame_t, accent, scale),
                    _quiz_panel(start, end, left, frame_y + frame_h - frame_t, card_width, frame_t, accent, scale),
                    _quiz_panel(start, end, left, frame_y, frame_t, frame_h, accent, scale),
                    _quiz_panel(start, end, right - frame_t, frame_y, frame_t, frame_h, accent, scale),
                ])
            choices = [str(choice) for choice in block.get("quiz_choices") or []]
            correct = int(block.get("quiz_correct_choice") or 0)
            choices_top = 0.515 if has_visual else 0.335
            for index, choice in enumerate(choices):
                choice_y = round(height * (choices_top + index * 0.058))
                row_h = round(height * 0.050)
                selected = phase == "reveal" and index == correct
                row_top = choice_y - row_h // 2
                shadow_offset = max(2, round(6 * scale))
                inset = max(2, round(3 * scale))
                fill = correct_colour if selected else card
                events.append(_quiz_panel(start, end, left + shadow_offset, row_top + shadow_offset,
                                          card_width, row_h, "#050914", scale))
                events.append(_quiz_panel(start, end, left, row_top, card_width, row_h,
                                          correct_colour if selected else accent, scale))
                events.append(_quiz_panel(start, end, left + inset, row_top + inset,
                                          card_width - inset * 2, row_h - inset * 2, fill, scale))
                badge_size = row_h - round(18 * scale)
                badge_x = left + round(14 * scale)
                badge_y = choice_y - badge_size // 2
                badge_colour = "#ffffff" if selected else accent
                events.append(_quiz_panel(start, end, badge_x, badge_y,
                                          badge_size, badge_size, badge_colour, scale))
                badge_text = f"{{\\an5\\pos({badge_x + badge_size // 2},{choice_y})\\fs{round(38 * scale)}\\bord0\\shad0\\1c{_ass_rgb(correct_colour if selected else _contrast_text(accent))}}}{letters[index]}"
                events.append(_dialogue(start, end, badge_text, "QuizQuestion", 3))
                text_x = badge_x + badge_size + round(24 * scale)
                right_reserve = round(72 * scale) if selected else round(28 * scale)
                # Centre the answer in the row: the usable half-width is bounded by
                # the badge on the left and the check mark (when shown) on the right.
                half = min(centre - text_x, right - right_reserve - centre)
                size, answer = _quiz_fit_text(choice, 2 * half, round(52 * scale), 2)
                colour = _ass_rgb("#ffffff" if selected else foreground)
                tags = f"{{\\an5\\pos({centre},{choice_y})\\fs{size}\\bord0\\shad0\\1c{colour}\\q2}}"
                events.append(_dialogue(start, end, tags + answer, "QuizCorrect" if selected else "QuizChoice", 2))
                if selected:
                    check = f"{{\\an5\\pos({right - round(38 * scale)},{choice_y})\\fs{round(42 * scale)}\\bord0\\shad0\\1c{_ass_rgb('#ffffff')}}}✓"
                    events.append(_dialogue(start, end, check, "QuizQuestion", 3))
            if phase == "question":
                countdown = int(block.get("hold_after_seconds") or 0)
                timer_start = max(start, end - countdown)
                timer_y = round(height * (0.748 if has_visual else 0.568))
                if countdown > 0 and timer_start < end:
                    # Smooth draining bar, timed to the actual audio hold.
                    bar_width = card_width - round(40 * scale)
                    milliseconds = max(1, round((end - timer_start) * 1000))
                    events.append(_quiz_panel(timer_start, end, left + round(20 * scale),
                                              round(height * (0.775 if has_visual else 0.595)),
                                              bar_width, max(2, round(7 * scale)),
                                              accent, scale, f"\\t(0,{milliseconds},\\fscx0)"))
                for remaining in range(countdown, 0, -1):
                    seg_start = max(start, end - remaining)
                    seg_end = min(end - remaining + 1, end)
                    if seg_start < seg_end:
                        timer = f"{{\\pos({centre},{timer_y})\\fs{round(64 * scale)}\\bord0\\shad0\\1c{_ass_rgb(accent)}}}{remaining}"
                        events.append(_dialogue(seg_start, seg_end, timer, "QuizTimer", 2))
        cursor = end
    return events


def _contrast_text(colour: str) -> str:
    value = colour.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#111827" if luminance > 0.62 else "#ffffff"


def _quiz_fit_text(text: str, width: int, font_size: int, max_lines: int) -> tuple[int, str]:
    """Wrap without truncating an answer; reduce type for unusually long text."""
    size = max(1, font_size)
    while True:
        lines = textwrap.wrap(" ".join(text.split()), width=max(1, int(width / (size * 0.65)))) or [""]
        if len(lines) <= max_lines or size == 1:
            return size, "\\N".join(_ass_escape(line) for line in lines)
        size -= 1


def _quiz_panel(start: float, end: float, x: int, y: int, width: int, height: int,
                colour: str, scale: float, animation: str = "") -> str:
    """Draw a rounded card with libass; no extra images or network calls."""
    radius = min(round(18 * scale), width // 2, height // 2)
    w, h, r = width, height, radius
    path = (f"m {r} 0 l {w-r} 0 b {w} 0 {w} 0 {w} {r} "
            f"l {w} {h-r} b {w} {h} {w} {h} {w-r} {h} "
            f"l {r} {h} b 0 {h} 0 {h} 0 {h-r} l 0 {r} b 0 0 0 0 {r} 0")
    tags = f"{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c{_ass_rgb(colour)}{animation}}}"
    return _dialogue(start, end, tags + path + "{\\p0}", "QuizPanel", 1)


# Black scrim opacity outside the illustration window (0x70 ~ 56% black).
_QUIZ_SCRIM_ALPHA = "70"


def _quiz_scrim(start: float, end: float, x: int, y: int, width: int, height: int, alpha_hex: str) -> str:
    """Square-cornered translucent black rectangle (ASS alpha: 00 opaque .. FF clear)."""
    path = f"m 0 0 l {width} 0 l {width} {height} l 0 {height}"
    tags = f"{{\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\1c&H000000&\\1a&H{alpha_hex}&}}"
    return _dialogue(start, end, tags + path + "{\\p0}", "QuizPanel", 0)


def _word_pop_events(cue: dict, preset: dict, fs_prefix: str, reset: str) -> list[str]:
    """Un Dialogue par fenêtre "mot en cours" : le texte complet du cue reste
    affiché, seul le mot actif passe en couleur `highlight_colour` et grossit.
    `fs_prefix` / `reset` portent la réduction de police éventuelle du cue."""
    words = cue["words"]
    hl = preset["highlight_colour"]
    events: list[str] = []
    for i, _word in enumerate(words):
        seg_start = cue["start"] if i == 0 else words[i]["start"]
        seg_end = words[i + 1]["start"] if i + 1 < len(words) else cue["end"]
        seg_start = max(seg_start, cue["start"])
        seg_end = max(seg_end, seg_start + 0.05)
        rendered = fs_prefix + " ".join(
            (f"{{\\1c{hl}\\fscx118\\fscy118}}{_ass_escape(w['text'])}{reset}" if j == i
             else _ass_escape(w["text"]))
            for j, w in enumerate(words)
        )
        events.append(_dialogue(seg_start, seg_end, rendered))
    return events


def _without_question_cues(cues: list[dict], blocks: list[dict], durations: list[float]) -> list[dict]:
    """Retire les sous-titres de narration qui tombent dans une phase
    « question » du quiz : la carte affiche déjà la question et les choix, les
    répéter en bas d'écran doublait le texte (et tombait dans la zone recouverte
    par l'interface). Les phases intro, révélation et conclusion gardent leurs
    sous-titres (l'explication n'est pas sur la carte)."""
    spans = []
    cursor = 0.0
    for block, duration in zip(blocks, durations):
        end = cursor + max(float(duration), 0.0)
        if block.get("quiz_phase") in {"cover", "question"}:
            spans.append((cursor, end))
        cursor = end
    if not spans:
        return cues
    return [
        cue for cue in cues
        # A cue crossing a phase boundary must not leak narration onto a card.
        if not any(cue["start"] < end and cue["end"] > start for start, end in spans)
    ]


def write_ass(
    cues: list[dict],
    out_path: str,
    style: str = DEFAULT_CAPTION_STYLE,
    resolution: str = "1080x1920",
    font: str | None = None,
    blocks: list[dict] | None = None,
    block_durations: list[float] | None = None,
) -> str:
    """Écrit un fichier `.ass` complet (style + événements) pour `style`. À
    passer tel quel au filtre `subtitles` d'ffmpeg (libass lit le style
    embarqué, pas besoin de `force_style`)."""
    captions_off = style == CAPTIONS_OFF
    preset = _CAPTION_STYLES.get(style, _CAPTION_STYLES[DEFAULT_CAPTION_STYLE])
    is_quiz = any(b.get("quiz_phase") for b in (blocks or []))
    # Les scènes Motion Graphics occupent le centre de l'écran et réservent la
    # bande basse aux sous-titres (motion_graphics/canvas.py SAFE_BOTTOM_RATIO).
    is_motion = any(b.get("motion_graphic") for b in (blocks or []))
    font = font or os.environ.get("SUBTITLE_FONT") or "Arial"
    try:
        width, height = (int(x) for x in resolution.lower().split("x"))
    except ValueError:
        width, height = 1080, 1920

    if is_quiz:
        # Reserve the centre for answer cards; explanations stay below them
        # and above platform controls, including with the word-pop style.
        preset = {
            **preset, "single_word": False,
            "font_size": max(1, round(72 * min(width / 1080, height / 1920))),
            "margin_v": round(height * 0.28),
        }

    base_fs = preset["font_size"]
    events: list[str] = []
    if captions_off:
        cues = []
    elif blocks and block_durations:
        cues = _without_question_cues(cues, blocks, block_durations)
    for cue in cues:
        if preset.get("single_word"):
            words = cue.get("words") or [{"text": cue["text"], "start": cue["start"], "end": cue["end"]}]
            for index, word in enumerate(words):
                text = _ass_escape(word["text"].upper())
                if not text:
                    continue
                start = max(cue["start"], word["start"])
                next_start = words[index + 1]["start"] if index + 1 < len(words) else cue["end"]
                end = min(cue["end"], next_start, word["end"] + 0.08)
                if end <= start:
                    continue
                # Scale against both axes, including square and landscape outputs.
                size = max(1, round(base_fs * min(width / 1080, height / 1920)))
                size = min(size, max(1, round(width * 0.8 / (max(len(text), 1) * 0.75))))
                outline = max(1, round(5 * size / 90))
                if is_motion:
                    # Bande basse, comme les autres styles : le centre est pris par la scène.
                    anchor = f"\\an2\\pos({width // 2},{height - round(preset['margin_v'] * height / 1920)})"
                else:
                    anchor = f"\\an5\\pos({width // 2},{height // 2})"
                tags = f"{{{anchor}\\fs{size}\\bord{outline}\\b1\\1c&HFFFFFF&}}"
                events.append(_dialogue(start, end, tags + text))
            continue
        text = _ass_escape(cue["text"])
        fs = _cue_font_size(text, base_fs)
        role_prefix = "{\\fad(45,70)}"
        if cue.get("role") == "hook":
            role_prefix = "{\\fad(35,60)\\fscx110\\fscy110\\1c&H0000D7FF&}"
        fs_prefix = role_prefix + ("" if fs == base_fs else f"{{\\fs{fs}}}")
        # `\r` seul remettrait la police pleine du style ; on ré-applique la
        # taille réduite après un reset.
        reset = "{\\r}" if fs == base_fs else f"{{\\r\\fs{fs}}}"
        if preset.get("word_highlight") and cue.get("words"):
            events.extend(_word_pop_events(cue, preset, fs_prefix, reset))
        else:
            events.append(_dialogue(cue["start"], cue["end"], fs_prefix + text))

    if blocks and block_durations:
        events = _quiz_events(blocks, block_durations, width, height) + events

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(
        _ass_header(width, height, preset, font, next((str(b.get("quiz_theme")) for b in (blocks or []) if b.get("quiz_theme")), "studio")) + "\n".join(events) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_srt(cues: list[dict], out_path: str) -> str:
    lines = []
    for cue in cues:
        lines.append(str(cue["index"]))
        lines.append(f"{format_timestamp(cue['start'])} --> {format_timestamp(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
