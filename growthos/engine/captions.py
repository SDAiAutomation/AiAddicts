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

# Couleurs ASS = &HAABBGGRR (alpha inversé : 00 = opaque). Tailles en pixels
# (PlayResX/Y = résolution vidéo réelle, cf. write_ass). MarginV pensé pour
# un cadre 1920 de haut, mis à l'échelle par libass pour les autres formats.
_CAPTION_STYLES: dict[str, dict] = {
    # Gros blanc gras, contour noir épais — le défaut, lisible sur tout fond.
    "bold_stroke": {
        "font_size": 108, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": -1, "border_style": 1, "outline_w": 7,
        "shadow": 0, "spacing": 0, "margin_v": 350,
    },
    # Plus fin, plus petit, interligne aéré, ombre douce — sobre.
    "sleek": {
        "font_size": 80, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": 0, "border_style": 1, "outline_w": 3,
        "shadow": 4, "spacing": 3, "margin_v": 360,
    },
    # Texte blanc sur bandeau noir semi-opaque (BorderStyle=3 = boîte).
    "boxed": {
        "font_size": 76, "primary": "&H00FFFFFF", "outline": "&HB3000000",
        "back": "&HB3000000", "bold": -1, "border_style": 3, "outline_w": 30,
        "shadow": 0, "spacing": 0, "margin_v": 360,
    },
    # Blanc + halo bleu accent (contour coloré + ombre portée colorée).
    "neon": {
        "font_size": 96, "primary": "&H00FFFFFF", "outline": "&H00EB6325",
        "back": "&H00EB6325", "bold": -1, "border_style": 1, "outline_w": 5,
        "shadow": 7, "spacing": 1, "margin_v": 350,
    },
    # Le mot en cours passe en jaune et grossit (look "MrBeast/Hormozi").
    "word_pop": {
        "font_size": 104, "primary": "&H00FFFFFF", "outline": "&H00000000",
        "back": "&H00000000", "bold": -1, "border_style": 1, "outline_w": 7,
        "shadow": 0, "spacing": 0, "margin_v": 350,
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


def build_cues(block_words: list[tuple[list[dict], float]], gap: float = 0.15) -> list[dict]:
    """`block_words` : une entrée par bloc, dans l'ordre de lecture —
    (mots du bloc [{"text","start","end"} relatifs au bloc], durée réelle
    du bloc en secondes, mesurée par ffprobe). La durée réelle (pas juste
    la fin du dernier mot) sert à décaler les blocs suivants, pour rester
    calé sur l'audio concaténé (video.concat_audio ne met aucun blanc entre
    blocs — un décalage ici dériverait de bloc en bloc).

    Regroupe les mots de chaque bloc par paquets de `_WORDS_PER_CUE`.

    Construit d'abord les bornes brutes de chaque groupe, puis leur applique
    la marge `gap` en une deuxième passe, bornée par le début du groupe
    *suivant* (bloc suivant compris) — sinon la marge d'un groupe peut
    déborder sur le début du suivant quand les mots s'enchaînent vite,
    produisant des cues qui se chevauchent dans le SRT."""
    raw: list[list] = []  # [start, end, text, words], sans la marge
    cursor = 0.0
    for words, block_duration in block_words:
        for start in range(0, len(words), _WORDS_PER_CUE):
            chunk = words[start:start + _WORDS_PER_CUE]
            text = " ".join(w["text"] for w in chunk)
            # Mots avec timing absolu (décalé du curseur bloc) — sert au
            # surlignage mot par mot des styles type "word_pop".
            abs_words = [
                {"text": w["text"], "start": cursor + w["start"], "end": cursor + w["end"]}
                for w in chunk
            ]
            raw.append([cursor + chunk[0]["start"], cursor + chunk[-1]["end"], text, abs_words])
        cursor += block_duration
    total_duration = cursor

    cues = []
    for i, (start, end, text, abs_words) in enumerate(raw):
        next_start = raw[i + 1][0] if i + 1 < len(raw) else total_duration
        cue_end = min(end + gap, next_start)
        cues.append({
            "index": i + 1, "start": start, "end": max(cue_end, start + 0.1),
            "text": text, "words": abs_words,
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


def _ass_header(width: int, height: int, preset: dict, font: str) -> str:
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
        f"Style: {style_fields}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _dialogue(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,{text}"


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


def write_ass(
    cues: list[dict],
    out_path: str,
    style: str = DEFAULT_CAPTION_STYLE,
    resolution: str = "1080x1920",
    font: str | None = None,
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
    for cue in cues:
        text = _ass_escape(cue["text"])
        fs = _cue_font_size(text, base_fs)
        fs_prefix = "" if fs == base_fs else f"{{\\fs{fs}}}"
        # `\r` seul remettrait la police pleine du style ; on ré-applique la
        # taille réduite après un reset.
        reset = "{\\r}" if fs == base_fs else f"{{\\r\\fs{fs}}}"
        if preset.get("word_highlight") and cue.get("words"):
            events.extend(_word_pop_events(cue, preset, fs_prefix, reset))
        else:
            events.append(_dialogue(cue["start"], cue["end"], fs_prefix + text))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(
        _ass_header(width, height, preset, font) + "\n".join(events) + "\n",
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
