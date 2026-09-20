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
from pathlib import Path

# 2-4 mots par écran (choisi avec l'utilisateur) : assez court pour bouger
# vite, assez long pour rester lisible.
_WORDS_PER_CUE = 3

DEFAULT_CAPTION_STYLE = "bold_stroke"

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
        "font_size": 108, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": -1, "border_style": 1, "outline_w": 7,
        "shadow": 0, "spacing": 0, "margin_v": 540,
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
    return name if name in _CAPTION_STYLES else DEFAULT_CAPTION_STYLE


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
_QUIZ_CHOICES_Y = 0.47
_QUIZ_TIMER_Y = 0.65


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
        if phase in {"question", "reveal"}:
            question = _ass_escape(str(block.get("quiz_question") or ""))
            number = int(block.get("quiz_question_number") or 0)
            total = int(block.get("quiz_question_total") or 0)
            if number and total:
                # Couleur du libellé = accent du thème (l'or d'avant était illisible sur les cartes blanches).
                label_colour = _ass_rgb(_QUIZ_THEME_COLOURS.get(str(block.get("quiz_theme")), _QUIZ_THEME_COLOURS["studio"])[3])
                question = f"{{\\fs34\\c{label_colour}}}QUESTION {number}/{total}{{\\rQuizQuestion}}\\N{question}"
            choices = [str(choice) for choice in block.get("quiz_choices") or []]
            events.append(_dialogue(start, end, f"{{\\fad(100,100)}}{question}", "QuizQuestion", 0))
            rendered_choices = "\\N\\N".join(
                f"{letters[i]}. {_ass_escape(choice)}" for i, choice in enumerate(choices)
            )
            choice_y = round(height * _QUIZ_CHOICES_Y)
            if phase == "reveal":
                correct = int(block.get("quiz_correct_choice") or 0)
                answer = f"✓ {letters[correct]}. {_ass_escape(choices[correct])}"
                events.append(_dialogue(start, end, f"{{\\pos({width // 2},{choice_y})\\fad(80,120)}}{answer}", "QuizCorrect", 1))
            else:
                events.append(_dialogue(start, end, f"{{\\pos({width // 2},{choice_y})\\fad(80,120)}}{rendered_choices}", "QuizChoice", 1))
                countdown = int(block.get("hold_after_seconds") or 0)
                timer_start = max(start, end - countdown)
                timer_y = round(height * _QUIZ_TIMER_Y)
                for remaining in range(countdown, 0, -1):
                    seg_start = timer_start + (countdown - remaining)
                    seg_end = min(seg_start + 1, end)
                    if seg_start < seg_end:
                        timer = f"{{\\pos({width // 2},{timer_y})\\fad(80,80)}}{remaining}"
                        events.append(_dialogue(seg_start, seg_end, timer, "QuizTimer", 1))
        cursor = end
    return events


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
        if block.get("quiz_phase") == "question":
            spans.append((cursor, end))
        cursor = end
    if not spans:
        return cues
    return [
        cue for cue in cues
        if not any(start <= (cue["start"] + cue["end"]) / 2 < end for start, end in spans)
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
    preset = _CAPTION_STYLES.get(style, _CAPTION_STYLES[DEFAULT_CAPTION_STYLE])
    font = font or os.environ.get("SUBTITLE_FONT") or "Arial"
    try:
        width, height = (int(x) for x in resolution.lower().split("x"))
    except ValueError:
        width, height = 1080, 1920

    base_fs = preset["font_size"]
    events: list[str] = []
    if blocks and block_durations:
        cues = _without_question_cues(cues, blocks, block_durations)
    for cue in cues:
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
