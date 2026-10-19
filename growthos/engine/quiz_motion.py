"""Opt-in quiz choreography on the existing libass/FFmpeg timeline.

No provider calls, generated code, new renderer or additional audio track.
All timings are relative to the measured narration block. Choices settle
before the existing silent reflection period; answer data is only used in
the reveal. Text is escaped and fitted with the classic renderer's helpers.
"""
from __future__ import annotations

import math
from pathlib import Path

VERSION = "quiz-motion:v6"
REVEAL_BEAT_SECONDS = 0.5

# Police de marque (celle de la miniature, engine/thumbnail.py). libass dimensionne `\fs` sur la hauteur de la
# cellule de la police (ascendante + descendante) : à taille de code égale Poppins s'affiche ~30 % plus petit
# qu'Arial (mesuré : capitales 53 px à 130 contre 63 px à 100). `size_k` rétablit la taille visuelle d'Arial ;
# `pitch` est l'interligne visuel que je pose moi-même, ligne par ligne, car l'interligne natif de Poppins est trop
# aéré (60 % de plus à capitales égales).
BRAND_FONT = "Poppins"
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONT_FILES = ("Poppins-Bold.ttf", "Poppins-Regular.ttf")
FONT_PROFILES = {"Poppins": {"size_k": 1.45, "pitch": 1.12}}


def font_profile(font: str | None) -> dict | None:
    """Corrections de taille d'une police de marque, ou None pour la police par défaut (Arial)."""
    return FONT_PROFILES.get(font or "")


def brand_font_available() -> bool:
    """Vrai si les fichiers de la police de marque sont livrés : sans eux libass retomberait sur une autre police
    avec des tailles corrigées pour Poppins, soit 45 % trop grandes."""
    return all((FONT_DIR / name).is_file() for name in FONT_FILES)

# Anneau du compte à rebours : 70 % du poids des sous-titres d'un quiz long (mesuré avec
# scripts/measure_quiz_motion.py). 12 images/s et 48 points suffisent à l'œil pour un anneau de 100 px.
TIMER_STEPS_PER_SECOND = 12
RING_POINTS = 48


_LIGHT_THEMES = {"minimal", "logo"}

# Un quiz long est découpé en 4 parties, chacune avec sa teinte de fond : sur 11 minutes, un fond qui ne change
# jamais est la première source de monotonie. Teintes très sombres (ou très claires), le texte garde son contraste.
PARTS = 4
MIN_QUESTIONS_FOR_PARTS = 10
_TINTS_DARK = ("#080e1c", "#071a1f", "#130d26", "#1f0c14")  # marine, sarcelle, indigo, bordeaux
_TINTS_LIGHT = ("#eef2f6", "#e8f4f2", "#f1eefa", "#fbeef0")
_TINTS_BOSS = ("#150a33", "#190c3b", "#12082c", "#1d0b34")  # violets profonds du « Final Boss »
_TINTS_SPLIT = ("#0a1030", "#0b1234", "#091029", "#0c1133")  # marine : seulement derrière les deux camps
SPLIT_LEFT, SPLIT_RIGHT = "#1740c9", "#cf3e14"  # bleu / orange ; blanc dessus : au moins 4,5:1 (vérifié par test)
_TINTS_VAULT = ("#0b0906", "#0d0a06", "#0a0806", "#0e0a07")  # noirs chauds : le coffre-fort ; l'or (accent) porte le reste
URGENT_COLOUR = "#f97316"  # les 2 dernières secondes du compte à rebours
URGENT_COLOUR_LIGHT = "#c2410c"  # même rôle sur scène claire : #f97316 n'y atteint que ~2,6:1, #c2410c ~5:1
# Coche dessinée dans une boîte de 100 x 100 (aucun glyphe unicode : il dépend de la police de repli).
_CHECK_POINTS = ((8, 54), (22, 40), (40, 58), (78, 18), (92, 32), (40, 86))
_SCENE_PHASES = {"intro", "question", "reveal", "outro"}


def uses_columns(width: int, height: int) -> bool:
    """Cadres larges (16:9) : question à gauche, réponses empilées à droite. Le carré garde la pile centrée."""
    return width >= height * 1.3


def column_layout(width: int) -> tuple[float, float, float, float]:
    """(x gauche, largeur de la colonne gauche, x de la colonne droite, x droit) de la mise en page en colonnes."""
    left, right = width * .08, width * .90
    left_w = (right - left) * .46
    return left, left_w, left + left_w + width * .033, right


def part_index(block: dict) -> int:
    """Partie (0 à 3) d'un bloc ; toujours 0 pour un quiz de moins de 10 questions."""
    total = int(block.get("quiz_question_total") or 0)
    if total < MIN_QUESTIONS_FOR_PARTS:
        return 0
    phase = block.get("quiz_phase")
    if phase == "intro":
        return 0
    if phase == "outro":
        return PARTS - 1
    number = max(1, int(block.get("quiz_question_number") or 1))
    return min(PARTS - 1, (number - 1) * PARTS // total)


def stage_background(theme: str | None, part: int = 0) -> str:
    """Couleur de la scène Motion (#rrggbb) ; les thèmes clairs ont une scène claire."""
    tints = _TINTS_LIGHT if theme in _LIGHT_THEMES else _TINTS_VAULT if theme == "vault" else _TINTS_BOSS if theme == "boss" else _TINTS_SPLIT if theme == "split" else _TINTS_DARK
    return tints[max(0, min(PARTS - 1, part))]


def base_background_for(script: dict, fade_duration: float, block: dict | None = None) -> str | None:
    """Couleur FFmpeg (`0xRRGGBB`) à donner au fond uni de la vidéo pour ce bloc, ou None.

    Dessiner la scène en rectangle plein écran dans libass coûte un mélange 1080p par image :
    mesuré à ~60 % du temps de rendu d'un quiz long. Quand la vidéo de base est déjà de la
    couleur de la scène, le rectangle devient inutile. Pas de fondu au noir entre les plans :
    il serait visible sans le rectangle qui le recouvrait. Sans `block`, la couleur de la partie 1."""
    info = presentation_info(script)
    if info is None or info["mode"] != "motion" or fade_duration > 0:
        return None
    if block is not None and block.get("quiz_phase") not in _SCENE_PHASES:
        return None
    part = part_index(block) if block is not None else 0
    return "0x" + stage_background((script.get("quiz") or {}).get("theme"), part)[1:].upper()


def _mix_hex(first: str, second: str, amount: float) -> str:
    a, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (first, second))
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def presentation_info(script: dict) -> dict | None:
    if script.get("content_format") != "quiz":
        return None
    mode = (script.get("quiz") or {}).get("presentation", "classic")
    return {"mode": mode, "version": VERSION if mode == "motion" else None,
            "renderer": "ffmpeg-libass"}


def build_timeline(script: dict, durations: list[float]) -> dict | None:
    """Describe measured audio timing, including the cover, without an AI call."""
    info = presentation_info(script)
    if info is None:
        return None
    blocks = script.get("blocks") or []
    if len(blocks) != len(durations):
        raise ValueError("Quiz : chaque bloc doit avoir une durée audio mesurée.")
    cover = (script.get("quiz") or {}).get("cover") or {}
    cursor = float(cover.get("duration_seconds", .8)) if cover.get("enabled") else 0.0
    scenes = []
    for index, (block, duration) in enumerate(zip(blocks, durations)):
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Quiz : durée audio invalide pour le bloc {index + 1}.")
        hold = float(block.get("hold_after_seconds") or 0)
        beat = max(0.0, float(block.get("quiz_reveal_beat_seconds") or 0)) if block.get("quiz_phase") == "question" else 0.0
        if not math.isfinite(hold) or not math.isfinite(beat) or hold < 0 or hold + beat > duration:
            raise ValueError(f"Quiz : la durée audio du bloc {index + 1} ne contient pas son temps de réflexion.")
        scene = {"block": index, "phase": block.get("quiz_phase"),
                 "startSeconds": round(cursor, 4), "endSeconds": round(cursor + duration, 4)}
        if block.get("quiz_phase") == "question":
            scene["reflectionStartSeconds"] = round(cursor + duration - hold - beat, 4)
            scene["reflectionSeconds"] = hold
            scene["entranceEnabled"] = info["mode"] == "motion" and duration - hold - beat >= 1
        scenes.append(scene)
        cursor += duration
    return {**info, "timingSource": "measured_audio", "totalDurationSeconds": round(cursor, 4),
            "coverSeconds": float(cover.get("duration_seconds", .8)) if cover.get("enabled") else 0,
            "scenes": scenes, "additionalProviderCalls": 0,
            "renderSeconds": None, "renderCostUsd": None, "reusedFinalVideo": False}


def attach_report(script: dict, report: dict) -> None:
    metadata = script.get("generationMetadata")
    script["generationMetadata"] = {**(metadata if isinstance(metadata, dict) else {}),
                                    "quizPresentation": report}


def scene_events(block: dict, start: float, end: float, width: int, height: int, font: str | None = None) -> list[str]:
    from .captions import _ass_rgb, _dialogue, _quiz_fit_text, _QUIZ_THEME_COLOURS

    if end <= start:
        return []
    phase = block["quiz_phase"]
    duration = end - start
    # The layout is authored for 9:16 (1080 wide). Landscape and square frames
    # are as wide as the reference but shorter, so `height / 1920` would shrink
    # every glyph to ~56 %; size them against the 1080 px reference instead.
    landscape = width >= height
    scale = height / 1080 if landscape else min(width / 1080, height / 1920)
    cx = width / 2
    left, right = width * .08, width * .90
    span = right - left
    # Theme remains independent of presentation. Light themes use a light stage.
    card, ink, correct, accent = _QUIZ_THEME_COLOURS.get(block.get("quiz_theme"), _QUIZ_THEME_COLOURS["studio"])
    channels = [int(correct[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    luminance = sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    selected_ink = "#000000" if luminance > .179 else "#ffffff"
    light = block.get("quiz_theme") in _LIGHT_THEMES
    background = stage_background(block.get("quiz_theme"), part_index(block))
    rail = "#cbd5e1" if light else "#243249"
    if not light:
        # Cartes plus claires que la scène (le bleu nuit du thème se fondait dans le fond) et cernées d'un
        # filet : la séparation reste visible sur un petit écran. Les thèmes clairs ont déjà des cartes blanches.
        card = _mix_hex(background, "#ffffff", .10)
    card_border = rail if light else _mix_hex(background, "#ffffff", .24)
    vault = block.get("quiz_theme") == "vault"
    boss = block.get("quiz_theme") == "boss"
    # Encre des réponses : cartes crème du Final Boss = texte sombre, le reste suit `ink`.
    card_ink, label_colour = ("#1a0f3a", "#5b2fc9") if boss else (ink, accent)
    if boss:
        card, card_border, rail = "#f3ead2", "#d9b43a", "#3a2670"
    if vault:
        # Coffre-fort : cartes noir chaud cernées d'un filet d'or terni, rail et fentes dans le même brun.
        card, card_border, rail = "#17120a", "#8a6a1f", "#3a2c10"
    events: list[str] = []
    profile = font_profile(font)

    def emit(a, b, tags, content, layer=2, style="QuizPanel"):
        a, b = max(start, a), min(end, b)
        if b > a:
            events.append(_dialogue(a, b, "{" + tags + "}" + content, style, layer))

    def position(x, y, origin=None, delay=0, travel=420):
        if origin is None:
            return f"\\pos({round(x)},{round(y)})"
        return (f"\\move({round(origin[0])},{round(origin[1])},{round(x)},{round(y)},{delay},{delay + travel})"
                f"\\alpha&HFF&\\t({delay},{delay + min(100, travel)},\\alpha&H00&)")

    def rect(a, b, x, y, w, h, colour, *, origin=None, delay=0, travel=420, layer=1, extra=""):
        w, h = max(1, round(w)), max(1, round(h))
        tags = f"\\an7{position(x,y,origin,delay,travel)}\\p1\\bord0\\shad0\\1c{_ass_rgb(colour)}{extra}"
        emit(a, b, tags, f"m 0 0 l {w} 0 {w} {h} 0 {h}{{\\p0}}", layer)

    def frame(a, b, x, y, w, h, edge, colour, *, origin=None, delay=0, travel=420, layer=1, extra=""):
        """Cadre d'épaisseur `edge` fait de quatre fines bandes. libass mélange à chaque image la boîte englobante
        de chaque forme, même creuse : un rectangle plein de plus coûte ~60 s de rendu pour un quiz long, un
        contour `\\bord` ~70 s, un cadre en tracé évidé autant (mesuré). Des bandes fines ne coûtent presque rien."""
        e = max(1.0, edge)
        shift = (lambda dx, dy: (origin[0] + dx, origin[1] + dy)) if origin else (lambda dx, dy: None)
        for bx, by, bw, bh in ((0, 0, w, e), (0, h - e, w, e), (0, e, e, h - 2 * e), (w - e, e, e, h - 2 * e)):
            rect(a, b, x + bx, y + by, bw, bh, colour, origin=shift(bx, by), delay=delay, travel=travel, layer=layer, extra=extra)

    def check(a, b, cx_, cy_, size, colour, *, origin=None, delay=0, travel=420, extra="", layer=3):
        """Coche dessinée (la police n'a pas de glyphe fiable) ; `size` = côté de sa boîte, centrée en (cx_, cy_)."""
        # `m` puis `l` : sans `l`, libass ne dessine rien (la coche de réponse n'apparaissait pas).
        first, *rest = (f"{round(px * size / 100)} {round(py * size / 100)}" for px, py in _CHECK_POINTS)
        points = f"{first} l {' '.join(rest)}"
        shift = (cx_ - size / 2, cy_ - size / 2)
        moved = (origin[0] - size / 2, origin[1] - size / 2) if origin else None
        tags = f"\\an7{position(shift[0], shift[1], moved, delay, travel)}\\p1\\bord0\\shad0\\1c{_ass_rgb(colour)}{extra}"
        emit(a, b, tags, f"m {points}{{\\p0}}{{check}}", layer)

    def text(a, b, value, x, y, size, colour, *, max_width=span, max_height=None, lines=2, origin=None, delay=0, travel=420, extra="", style="QuizQuestion", layer=3, steps=None):
        if steps:
            # Tailles discrètes plutôt qu'un rétrécissement continu : deux questions de longueurs voisines
            # gardent la même taille, le rythme visuel reste régulier sur 25 questions.
            for step in steps:
                fs, content = _quiz_fit_text(str(value), round(max_width), max(1, round(step * scale)), lines)
                if fs >= round(step * scale):
                    break
        else:
            fs, content = _quiz_fit_text(str(value), round(max_width), max(1, round(size * scale)), lines)
        if max_height is not None:
            fitted = min(fs, max(1, int(max_height / ((content.count(r"\N") + 1) * 1.25))))
            fs, content = _quiz_fit_text(str(value), round(max_width), fitted, lines)
        # Jamais de ponctuation seule sur la dernière ligne (« ? » orphelin) : on la rattache au mot précédent.
        head, _, last = content.rpartition(r"\N")
        if head and last.strip() in {"?", "!", ":", ";", "…", "?!"}:
            content = f"{head} {last.strip()}"
        if profile:
            # Une ligne = un événement, à l'interligne visuel voulu (voir FONT_PROFILES).
            parts = content.split(r"\N")
            for index, part in enumerate(parts):
                dy = (index - (len(parts) - 1) / 2) * fs * profile["pitch"]
                moved = (origin[0], origin[1] + dy) if origin else None
                tags = (f"\\an5{position(x, y + dy, moved, delay, travel)}\\fs{round(fs * profile['size_k'])}"
                        f"\\bord0\\shad0\\b1\\q2\\1c{_ass_rgb(colour)}{extra}")
                emit(a, b, tags, part, layer, style)
            return
        tags = f"\\an5{position(x,y,origin,delay,travel)}\\fs{fs}\\bord0\\shad0\\b1\\q2\\1c{_ass_rgb(colour)}{extra}"
        emit(a, b, tags, content, layer, style)

    def ring(a, b, x, y, radius, colour, extra="", portion=1.0):
        # Filled polygonal annulus: deterministic vectors, no font dependency.
        outer, inner = radius, max(1, radius - max(2, 4 * scale))
        count = max(3, round(RING_POINTS * portion))
        angles = [-math.pi / 2 + i / count * 2 * math.pi * portion for i in range(count + 1)]
        points = [(outer * math.cos(t), outer * math.sin(t)) for t in angles]
        points += [(inner * math.cos(t), inner * math.sin(t)) for t in reversed(angles)]
        path = "m " + " l ".join(f"{round(px)} {round(py)}" for px, py in points)
        emit(a, b, f"\\an7\\pos({round(x)},{round(y)})\\p1\\bord0\\shad0\\1c{_ass_rgb(colour)}{extra}", path + "{\\p0}", 2)

    def vault_slots(number: int, total: int, phase_: str) -> None:
        """En-tête « The Vault » : plaque, une case par question (chiffre du code ou cadenas) et plaque de question.
        Les chiffres sont décoratifs (un code de coffre, pas une donnée) ; la case de la question se déverrouille
        à la révélation. Au-delà de 8 questions les cases deviendraient illisibles : repli sur le compteur discret."""
        gold, dim = accent, "#6b5420"
        plaque_w, plaque_h = 400 * scale, 64 * scale
        frame(start, end, cx - plaque_w / 2, height * .032, plaque_w, plaque_h, max(2, 3 * scale), gold)
        text(start, end, "THE VAULT", cx, height * .032 + plaque_h / 2, 40, gold, lines=1, max_width=plaque_w - 30 * scale)
        if total <= 8:
            size = min(110 * scale, (span - (total - 1) * 14 * scale) / total)
            row_w = total * size + (total - 1) * 14 * scale
            x0, y0 = cx - row_w / 2, height * .092
            for i in range(total):
                x = x0 + i * (size + 14 * scale)
                unlocked = i < number - 1 or (phase_ == "reveal" and i == number - 1)
                current = i == number - 1
                frame(start, end, x, y0, size, size, max(2, (4 if current else 3) * scale), gold if unlocked or current else dim)
                if unlocked:
                    pop = "\\fscx140\\fscy140\\t(0,350,0.4,\\fscx100\\fscy100)" if current else ""
                    text(start, end, (7 + 6 * i) % 10, x + size / 2, y0 + size / 2, 64, gold, lines=1, max_width=size, extra=pop)
                else:
                    # Cadenas dessiné : corps plein et anse en U faite de trois fines bandes.
                    colour = gold if current else dim
                    body_w, body_h = size * .46, size * .32
                    bx, by = x + (size - body_w) / 2, y0 + size * .46
                    rect(start, end, bx, by, body_w, body_h, colour, layer=2)
                    arm = max(2, size * .06)
                    sx, sy, sw, sh = bx + body_w * .16, y0 + size * .22, body_w * .68, size * .26
                    rect(start, end, sx, sy, arm, sh, colour, layer=2)
                    rect(start, end, sx + sw - arm, sy, arm, sh, colour, layer=2)
                    rect(start, end, sx, sy, sw, arm, colour, layer=2)
            label_y = y0 + size + height * .027
        else:
            label_y = height * .092 + height * .03
        if phase_ == "reveal":
            return  # la question remonte pendant la révélation : la plaque la chevaucherait
        q_w, q_h = 340 * scale, 52 * scale
        frame(start, end, cx - q_w / 2, label_y, q_w, q_h, max(2, 2 * scale), dim)
        text(start, end, f"QUESTION {number} / {total}", cx, label_y + q_h / 2, 28, ink, lines=1, max_width=q_w - 24 * scale)

    def boss_ladder(number: int, total: int, phase_: str) -> None:
        """En-tête « Final Boss » : plaque, pastille « n / N » et rangée de niveaux sous la pastille
        (coche = passé, jaune = en cours, couronne = le boss, dernier niveau). Au-delà de 8 niveaux la rangée
        deviendrait illisible : plaque et pastille seulement. La rangée reste au centre : les Shorts rognent
        ~5 % de chaque bord sur les téléphones allongés (une marge à 4 % était coupée)."""
        gold, dim, deep = "#ffd23f", "#5a3fa0", "#2a1760"
        plaque_w, plaque_h = 400 * scale, 64 * scale
        frame(start, end, cx - plaque_w / 2, height * .032, plaque_w, plaque_h, max(2, 3 * scale), gold)
        text(start, end, "FINAL BOSS", cx, height * .032 + plaque_h / 2, 40, gold, lines=1, max_width=plaque_w - 30 * scale)
        q_w, q_h = 240 * scale, 56 * scale
        q_y = height * .105
        frame(start, end, cx - q_w / 2, q_y, q_w, q_h, max(2, 2 * scale), dim)
        text(start, end, f"{number} / {total}", cx, q_y + q_h / 2, 32, gold, lines=1, max_width=q_w - 24 * scale)
        if total > 8:
            return
        d, gap_ = 46 * scale, 16 * scale
        x0, y = cx - (total * d + (total - 1) * gap_) / 2 + d / 2, height * .165
        for i in range(total):
            x = x0 + i * (d + gap_)
            current, last = i == number - 1 and phase_ != "reveal", i == total - 1
            done = i < number - 1 or (phase_ == "reveal" and i == number - 1)
            disc = "m " + " l ".join(f"{round(d / 2 + d / 2 * math.cos(t / 20 * 2 * math.pi))} {round(d / 2 + d / 2 * math.sin(t / 20 * 2 * math.pi))}" for t in range(20))
            fill = gold if (done or current) else deep
            emit(start, end, f"\\an7\\pos({round(x - d / 2)},{round(y - d / 2)})\\p1\\bord0\\shad0\\1c{_ass_rgb(fill)}", disc + "{\\p0}", 2)
            if last:
                crown = ((10, 82), (10, 34), (30, 56), (50, 18), (70, 56), (90, 34), (90, 82))
                path = "m " + " l ".join(f"{round(px * d * .6 / 100)} {round(py * d * .6 / 100)}" for px, py in crown)
                emit(start, end, f"\\an7\\pos({round(x - d * .3)},{round(y - d * .28)})\\p1\\bord0\\shad0\\1c{_ass_rgb('#1a0f3a' if current else gold if done else dim)}", path + "{\\p0}", 3)
            elif done:
                check(start, end, x, y, d * .55, "#1a0f3a")
            else:
                text(start, end, i + 1, x, y, 26, "#1a0f3a" if current else dim, lines=1, max_width=d)

    def split_scene(choices, number, total, correct_index, hold_, tend_):
        """« Split Decision » : deux camps pleine hauteur (bleu / orange), une lettre géante et la réponse dans chacun,
        le minuteur à la jointure. Seulement pour deux réponses en vertical (vrai/faux, comparaison) ; sans image
        par choix pour l'instant. À la révélation le camp juste garde sa couleur, l'autre s'assombrit."""
        half = width / 2
        sides = ((0, SPLIT_LEFT), (half, SPLIT_RIGHT))
        cream, yellow = "#f8f0dc", "#ffe14d"
        for index, (x0, colour) in enumerate(sides):
            rect(start, end, x0, 0, half, height, colour, layer=0)
            if phase == "reveal" and index != correct_index:
                rect(start, end, x0, 0, half, height, "#05081a", layer=1, extra="\\alpha&H4C&")
        text(start, end, "SPLIT DECISION", cx, height * .036, 30, cream, lines=1, max_width=span, extra="\\fsp6")
        pill_w, pill_h = 190 * scale, 56 * scale
        rect(start, end, cx - pill_w / 2, height * .066, pill_w, pill_h, cream, layer=2)
        text(start, end, f"{number} / {total}", cx, height * .066 + pill_h / 2, 32, "#0b1030", lines=1, max_width=pill_w - 20 * scale)
        text(start, end, block.get("quiz_question", ""), cx, height * .19, 88, "#ffffff", lines=3, max_height=height * .19,
             steps=(88, 74, 62, 54), max_width=span)
        for index, (x0, colour) in enumerate(sides):
            centre = x0 + half / 2
            tint = _mix_hex(colour, "#ffffff", .30)
            if phase == "reveal" and index == correct_index:
                check(start, end, centre, height * .40, 230 * scale, "#ffffff", extra="\\fscx60\\fscy60\\t(0,300,0.4,\\fscx100\\fscy100)")
            else:
                text(start, end, "AB"[index], centre, height * .40, 300, tint, lines=1, max_width=half)
            text(start, end, choices[index], centre, height * .59, 74, "#ffffff", lines=3, max_height=height * .17,
                 steps=(74, 62, 52, 44), max_width=half - 90 * scale, style="QuizChoice")
        if phase == "question" and hold_ > 0:
            radius, ring_y = 78 * scale, height * .49
            timer_start = max(start, tend_ - hold_)
            steps = max(1, math.ceil((tend_ - timer_start) * TIMER_STEPS_PER_SECOND))
            urgent_from = tend_ - 2 if hold_ >= 3 else None
            disc = "m " + " l ".join(f"{round(radius * math.cos(t / 28 * 2 * math.pi))} {round(radius * math.sin(t / 28 * 2 * math.pi))}" for t in range(28))
            emit(timer_start, tend_, f"\\an7\\pos({round(cx)},{round(ring_y)})\\p1\\bord0\\shad0\\1c{_ass_rgb('#0b1030')}", disc + "{\\p0}", 2)
            for j in range(steps):
                a = timer_start + (tend_ - timer_start) * j / steps
                b = timer_start + (tend_ - timer_start) * (j + 1) / steps
                ring(a, b, cx, ring_y, radius, yellow if urgent_from is not None and a >= urgent_from else cream, portion=max(.001, 1 - j / steps))
            for remaining in range(math.ceil(min(hold_, duration)), 0, -1):
                a, b = max(timer_start, tend_ - remaining), tend_ - remaining + 1
                text(a, b, remaining, cx, ring_y, 66, yellow if urgent_from is not None and remaining <= 2 else "#ffffff",
                     lines=1, max_width=radius * 1.5, style="QuizTimer", extra="\\fscx125\\fscy125\\t(0,160,0.4,\\fscx100\\fscy100)")
        if total <= 10:
            dot, gap_ = 22 * scale, 18 * scale
            x0 = cx - (total * dot + (total - 1) * gap_) / 2
            for i in range(total):
                rect(start, end, x0 + i * (dot + gap_), height * .925, dot, dot, cream if i < number else _mix_hex("#0b1030", "#ffffff", .25), layer=2)

    # Preserve the illustration as a real window; never substitute invented
    # factual diagrams for a supplied image/logo question.
    visual = bool(block.get("quiz_visual_available")) and phase in {"question", "reveal"}
    columns = uses_columns(width, height) and not visual
    if visual:
        top, bottom = height * .29, height * .435
        rect(start, end, 0, 0, width, top, background, layer=0)
        rect(start, end, 0, bottom, width, height - bottom, background, layer=0)
        rect(start, end, 0, top, left, bottom - top, background, layer=0)
        rect(start, end, right, top, width - right, bottom - top, background, layer=0)
        rect(start, end, left, bottom - max(2, 3 * scale), span, max(2, 3 * scale), accent)
    elif str(block.get("quiz_base_background") or "").lower() != background:
        # La vidéo de base n'est pas déjà de la couleur de la scène (voir base_background_for).
        rect(start, end, 0, 0, width, height, background, layer=0)

    # A typographic broadcast identity. The motion belongs to entrances and
    # reveals; nothing animates the answer cards during the reflection window.
    def contrast(colour):
        rgb = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return "#080e1c" if sum(c * w for c, w in zip(linear, (.2126, .7152, .0722))) > .179 else "#ffffff"

    accent_ink = contrast(accent)
    # Corner crop marks create a stage without a generic box around everything.
    vault_header = (vault or boss) and not landscape and phase in {"question", "reveal"}
    split_on = block.get("quiz_theme") == "split" and not landscape and not visual and len(block.get("quiz_choices") or []) == 2
    for x, direction in (() if vault_header or split_on else ((left, 1), (right, -1))):
        rect(start, end, x - (20 * scale if direction < 0 else 0), height * .105,
             20 * scale, 3 * scale, accent)
        rect(start, end, x, height * .105, 3 * scale, 20 * scale, accent)
    if phase in {"intro", "outro"}:
        title = str(block.get("quiz_topic") or "QUIZ").upper()
        settle = min(650, round(duration * 250))
        # Oversize outlined type and a moving cut strip are a single authored
        # entrance, not perpetual motion behind readable content.
        text(start, end, "QUIZ", cx, height * .29, 255, ink, lines=1,
             extra=f"\\1a&HFF&\\bord{2 * scale:.1f}\\3c{_ass_rgb(rail)}", layer=1)
        if phase == "intro":
            text(start, end, "QUIZ", cx, height * .30, 216, ink,
                 lines=1, origin=(cx - span * .12, height * .30), travel=settle,
                 extra=f"\\fscx112\\t(0,{settle},0.4,\\fscx100)")
        else:
            check(start, end, cx, height * .30, 216 * scale * .9, ink,
                  origin=(cx - span * .12, height * .30), travel=settle)
        rect(start, end, left, height * .415, span, height * .038, accent,
             extra=f"\\fscx0\\t(0,{settle},0.4,\\fscx100)")
        # Abstract orbit marks, never a fabricated scientific diagram or score.
        for i in range(8):
            angle = i * 45
            rect(start, end, cx - 3 * scale, height * .30 - 172 * scale,
                 6 * scale, 16 * scale, accent,
                 extra=f"\\org({round(cx)},{round(height * .30)})\\frz{angle - 35}\\t(0,{settle},0.4,\\frz{angle})")
        text(start, end, title, cx, height * .545, 98, ink, lines=3, max_height=height * .15,
             origin=(cx, height * .585), delay=100, travel=settle)
        return events

    choices = [str(c) for c in block.get("quiz_choices") or []]
    number = int(block.get("quiz_question_number") or 1)
    total = max(number, int(block.get("quiz_question_total") or number))
    hold = max(0.0, float(block.get("hold_after_seconds") or 0))
    # Suspense : le minuteur s'arrête `beat` secondes avant la fin du bloc ; les cartes restent figées, sans compte à rebours.
    beat = max(0.0, float(block.get("quiz_reveal_beat_seconds") or 0)) if phase == "question" else 0.0
    tend = end - beat
    animate = phase == "question" and duration - hold - beat >= 1.0
    correct_index = int(block.get("quiz_correct_choice") or 0) if phase == "reveal" else -1
    if (block.get("quiz_theme") == "split" and not landscape and not visual and len(choices) == 2
            and phase in {"question", "reveal"}):
        split_scene(choices, number, total, correct_index, hold, tend)
        return events
    # Offsets follow the type size in landscape, where `span` is far wider than
    # the glyphs and fractions of it would push "/ 03" away from "01".
    if vault_header:
        (boss_ladder if boss else vault_slots)(number, total, phase)
    else:
        number_x, total_x = (left + 80 * scale, left + 160 * scale) if landscape else (left + span * .09, left + span * .17)
        text(start, end, f"{number:02d}", number_x, height * .145, 74, ink, lines=1, max_width=span * .18)
        text(start, end, f"/ {total:02d}", total_x, height * .15, 30, accent, lines=1, max_width=span * .13)
        gap = 7 * scale
        if total > 12:
            # Au-delà de 12 questions, 25 segments deviennent un pointillé illisible : une barre continue.
            rect(start, end, right - span * .46, height * .146, span * .46, 7 * scale, rail)
            rect(start, end, right - span * .46, height * .146, span * .46 * number / total, 7 * scale, accent)
        else:
            segment = (span * .46 - (total - 1) * gap) / total
            for i in range(total):
                rect(start, end, right - span * .46 + i * (segment + gap), height * .146,
                     segment, 7 * scale, accent if i < number else rail)

    if columns:
        # 16:9 : le cadre est large et bas. Lecture en deux temps : la question à gauche (elle mène), les
        # réponses empilées à droite (elles soutiennent) ; le compte à rebours reste en périphérie, sous la
        # question. Les réponses ne bougent pas à la révélation : seule la bonne passe au vert, et la réponse
        # apparaît en grand à gauche.
        col_left, left_w, col_x, _ = column_layout(width)
        col_w = right - col_x
        left_cx = col_left + left_w / 2
        count = max(1, len(choices))
        band_top, band_bottom, row_gap = height * .215, height * .925, height * .02
        row_h = min(height * .19, (band_bottom - band_top - (count - 1) * row_gap) / count)
        rows_top = band_top + (band_bottom - band_top - (count * row_h + (count - 1) * row_gap)) / 2
        question_cy = height * .40
        if phase == "question":
            text(start, end, block.get("quiz_question", ""), left_cx, question_cy, 64, ink, lines=5, max_width=left_w,
                 max_height=height * .34, steps=(64, 56, 48),
                 origin=(left_cx - 50 * scale, question_cy) if animate else None, travel=350,
                 extra="\\fscx96\\fscy96\\t(0,350,0.5,\\fscx100\\fscy100)" if animate else "")
        else:
            text(start, end, block.get("quiz_question", ""), left_cx, height * .275, 44, ink, lines=3, max_width=left_w,
                 max_height=height * .15, steps=(44, 40, 36))
        for i, choice in enumerate(choices):
            y = rows_top + i * (row_h + row_gap)
            selected = i == correct_index
            delay, travel = i * 65, 380
            origin = (col_x + 70 * scale, y) if animate else None
            if selected:
                rect(start, end, col_x, y, col_w, row_h, correct, origin=origin, delay=delay, travel=travel)
                check(start, end, col_x + (18 + 32) * scale, y + row_h / 2, 34 * scale, selected_ink,
                      origin=(origin[0] + (18 + 32) * scale, origin[1] + row_h / 2) if origin else None, delay=delay, travel=travel)
            else:
                rect(start, end, col_x, y, col_w, row_h, card, origin=origin, delay=delay, travel=travel)
                frame(start, end, col_x, y, col_w, row_h, max(2, 2 * scale), card_border,
                      origin=origin, delay=delay, travel=travel, layer=2)
                chip = min(row_h * .62, 64 * scale)
                chip_x, chip_y = col_x + 18 * scale, y + (row_h - chip) / 2
                chip_origin = (chip_x + (origin[0] - col_x), chip_y + (origin[1] - y)) if origin else None
                rect(start, end, chip_x, chip_y, chip, chip, accent, origin=chip_origin, delay=delay, travel=travel, layer=2)
                text(start, end, "ABCD"[i], chip_x + chip / 2, chip_y + chip / 2 + chip * .03, chip * .62 / scale, accent_ink,
                     max_width=chip, lines=1,
                     origin=(chip_x + chip / 2 + chip_origin[0] - chip_x, chip_y + chip / 2 + chip_origin[1] - chip_y) if origin else None,
                     delay=delay, travel=travel)
            answer_x = col_x + col_w / 2 + 40 * scale
            text(start, end, choice, answer_x, y + row_h / 2, 50, selected_ink if selected else card_ink,
                 max_width=col_w - 196 * scale, max_height=row_h * .86,
                 origin=(answer_x + (origin[0] - col_x), y + row_h / 2 + (origin[1] - y)) if origin else None,
                 delay=delay, travel=travel, style="QuizCorrect" if selected else "QuizChoice")
        if phase == "question":
            radius = 64 * scale
            ring_y = height * .79
            urgent_from = tend - 2 if hold >= 3 else None
            if hold > 0:
                timer_start = max(start, tend - hold)
                steps_n = max(1, math.ceil((tend - timer_start) * TIMER_STEPS_PER_SECOND))
                for j in range(steps_n):
                    a = timer_start + (tend - timer_start) * j / steps_n
                    b = timer_start + (tend - timer_start) * (j + 1) / steps_n
                    ring(a, b, left_cx, ring_y, radius, (URGENT_COLOUR_LIGHT if light else URGENT_COLOUR)
                         if urgent_from is not None and a >= urgent_from else accent, portion=max(.001, 1 - j / steps_n))
                for remaining in range(math.ceil(min(hold, duration)), 0, -1):
                    a, b = max(timer_start, tend - remaining), tend - remaining + 1
                    text(a, b, remaining, left_cx, ring_y, 62, (URGENT_COLOUR_LIGHT if light else URGENT_COLOUR)
                         if urgent_from is not None and remaining <= 2 else ink, max_width=radius * 1.5, lines=1,
                         style="QuizTimer", extra="\\fscx125\\fscy125\\t(0,160,0.4,\\fscx100\\fscy100)")
                strip_y = height * .915
                rect(timer_start, tend, col_left, strip_y, left_w, 5 * scale, rail)
                rect(timer_start, tend, col_left, strip_y, left_w, 5 * scale, accent,
                     extra=f"\\fscx100\\t(0,{round((tend - timer_start) * 1000)},\\fscx0)")
        else:
            hero_y, hero_h = height * .525, height * .27
            rect(start, end, col_left, hero_y - hero_h / 2, left_w, hero_h, accent, layer=2,
                 extra="\\fscx0\\t(0,300,0.4,\\fscx100)")
            answer = choices[correct_index] if 0 <= correct_index < len(choices) else ""
            source_y = rows_top + max(0, correct_index) * (row_h + row_gap) + row_h / 2
            text(start, end, answer, left_cx, hero_y, 84, accent_ink, max_width=left_w - 80 * scale, lines=3,
                 max_height=hero_h * .80, origin=(col_x, source_y), travel=min(380, round(duration * 250)),
                 extra="\\fscx78\\fscy78\\t(0,380,0.4,\\fscx100\\fscy100)", steps=(84, 72, 60, 52))
            burst_end = min(end, start + .48)
            for direction in (-1, 1):
                for j in range(3):
                    rect(start, burst_end, left_cx + direction * (left_w / 2 - 12 * scale), hero_y + (j - 1) * 18 * scale,
                         5 * scale, 5 * scale, accent, origin=(left_cx + direction * left_w * .3, hero_y), travel=350,
                         layer=3, extra="\\fad(0,160)")
        return events

    # Four choices get an editorial 2x2 composition; long answers and image
    # questions keep full-width rails. Both share the same stable card language.
    # Une réponse de plus de ~30 caractères tomberait sous 2 % de la hauteur dans une demi-largeur en vertical
    # (mesuré avec tests/test_quiz_motion_layout.py) : pleine largeur au-delà. En paysage les cartes sont
    # assez larges et hautes pour 52 caractères sur deux lignes.
    question_grid = not visual and len(choices) in {2, 4} and max((len(c) for c in choices), default=0) <= (52 if landscape else 30)
    focus_reveal = phase == "reveal" and not visual

    def question_rows(count: int) -> tuple[float, float, float]:
        """(hauteur, pas, y de départ) des réponses pendant la question, sans illustration."""
        if landscape:
            # Le cadre est large et bas : cartes plus hautes pour que deux lignes restent lisibles.
            # Les cartes occupent la hauteur disponible sous la question (jusqu'à ~85 %) : un cadre 16:9 dont
            # le tiers bas reste vide paraît inachevé.
            return ((height * .21, height * .235, height * .40) if question_grid else
                    (height * (.115 if count == 4 else .13), height * (.135 if count == 4 else .15), height * .395))
        return (height * (.090 if question_grid else .055 if count == 4 else .063),
                height * (.103 if question_grid else .066 if count == 4 else .076),
                height * (.415 if question_grid else .375))

    grid = question_grid and not focus_reveal
    if visual:
        row_h, row_step, rows_y = height * .040, height * .048, height * .455
    else:
        row_h, row_step, rows_y = question_rows(len(choices))
    card_w = (span - 16 * scale) / 2 if grid else span
    if focus_reveal:
        # The grid folds into a compact answer key. This frees the centre for
        # the payoff instead of adding yet another label under the same slide.
        rows_y, row_h, row_step = height * .505, height * .034, height * .043
        if landscape:
            # Taller rows keep answers legible; the last row still ends above the caption band.
            rows_y, row_h, row_step = height * .56, height * .06, height * .07
    question_y = height * (.224 if visual else .225 if focus_reveal else .277)
    text(start, end, block.get("quiz_question", ""), cx, question_y, 64 if visual else 46 if focus_reveal else 76,
         ink, lines=3, max_height=height * (.09 if focus_reveal else .105 if visual else .17),
         steps=None if visual or focus_reveal else (76, 64, 54),
         # En paysage le compte à rebours occupe la droite de la ligne de la question.
         max_width=span - 2 * 168 * scale if landscape and phase == "question" else span,
         origin=(cx, height * .277) if focus_reveal else (cx, question_y + height * .025) if animate else None,
         travel=350,
         extra="\\fscx135\\fscy135\\t(0,350,0.4,\\fscx100\\fscy100)" if focus_reveal else
               "\\fscx96\\fscy96\\t(0,350,0.5,\\fscx100\\fscy100)" if animate else "")

    # Preserve the submitted order and never use the answer index before reveal.
    for i, choice in enumerate(choices):
        y = rows_y + (i // 2 if grid else i) * row_step
        x = left + (i % 2) * (card_w + 16 * scale) if grid else left
        selected = i == correct_index
        delay, travel = i * 65, 380
        origin = (x, y + height * .055) if animate else None
        old_card_w = (span - 16 * scale) / 2 if question_grid else span
        old_row_h, old_step, old_y0 = question_rows(len(choices))
        old_x = left + (i % 2) * (old_card_w + 16 * scale) if question_grid else left
        old_y = old_y0 + (i // 2 if question_grid else i) * old_step
        fold = ""
        if focus_reveal:
            delay = 0
            origin = (old_x, old_y)
            fold = (f"\\fscx{old_card_w / card_w * 100:.1f}\\fscy{old_row_h / row_h * 100:.1f}"
                    f"\\t(0,{travel},0.4,\\fscx100\\fscy100)")
        fill = correct if selected else card
        # Élévation déclarée une seule fois : le filet. Ni ombre dure décalée, ni barre colorée sur le côté
        # (la pastille de lettre porte l'accent). Le filet est un cadre creux (voir `frame`).
        if selected:
            rect(start, end, x, y, card_w, row_h, fill, origin=origin, delay=delay, travel=travel, extra=fold)
        else:
            rect(start, end, x, y, card_w, row_h, fill, origin=origin, delay=delay, travel=travel, extra=fold)
            frame(start, end, x, y, card_w, row_h, max(2, 2 * scale), card_border,
                  origin=origin, delay=delay, travel=travel, extra=fold, layer=2)
        label_x, label_y = x + (30 if grid else 35) * scale, y + row_h * (.23 if grid else .5)
        label_origin = (label_x, label_y + height * .055) if origin else None
        if focus_reveal:
            label_origin = (old_x + (30 if question_grid else 35) * scale,
                            old_y + old_row_h * (.23 if question_grid else .5))
        if selected:
            mark = (30 if grid or (landscape and focus_reveal) else 36) * scale
            check(start, end, label_x, label_y, mark, selected_ink, origin=label_origin, delay=delay, travel=travel)
        elif focus_reveal:
            text(start, end, "ABCD"[i], label_x, label_y, 26 if grid or landscape else 34,
                 label_colour, max_width=52 * scale, lines=1, origin=label_origin, delay=delay, travel=travel)
        else:
            # Pastille pleine, comme sur la miniature : la lettre se lit d'un coup d'œil, même en petit.
            chip = min(row_h * (.40 if grid else .62), ((52 if landscape else 44) if grid else 64) * scale)
            chip_x = x + (14 if grid else 18) * scale
            chip_y = y + (12 * scale if grid else (row_h - chip) / 2)
            chip_origin = (chip_x + origin[0] - x, chip_y + origin[1] - y) if origin else None
            rect(start, end, chip_x, chip_y, chip, chip, accent, origin=chip_origin, delay=delay, travel=travel, layer=2)
            text(start, end, "ABCD"[i], chip_x + chip / 2, chip_y + chip / 2 + chip * .03, chip * .62 / scale, accent_ink,
                 max_width=chip, lines=1,
                 origin=(chip_x + chip / 2 + chip_origin[0] - chip_x, chip_y + chip / 2 + chip_origin[1] - chip_y) if origin else None,
                 delay=delay, travel=travel)
        answer_x = x + card_w / 2 + (0 if grid else 22 * scale)
        answer_y = y + row_h * (.61 if grid else .5)
        answer_origin = (answer_x, answer_y + height * .055) if origin else None
        if focus_reveal:
            answer_origin = (old_x + old_card_w / 2 + (0 if question_grid else 22 * scale),
                             old_y + old_row_h * (.61 if question_grid else .5))
        text(start, end, choice, answer_x, answer_y, (54 if grid else 50) if landscape and not focus_reveal else 43 if grid else 44,
             selected_ink if selected else card_ink, max_width=card_w - (44 if grid else 150) * scale,
             max_height=row_h * (.52 if grid else .86),
             origin=answer_origin, delay=delay, travel=travel,
             style="QuizCorrect" if selected else "QuizChoice")

    if phase == "question":
        timer_start = max(start, tend - hold)
        radius = (64 if landscape else 57) * scale
        urgent_colour = URGENT_COLOUR_LIGHT if light else URGENT_COLOUR
        urgent_from = None
        # Portrait : sous les réponses. Paysage : à droite de la question (les réponses occupent la hauteur),
        # avec le trait de temps juste sous elle.
        timer_x, timer_y = (right - radius - 6 * scale, height * .277) if landscape else (cx, height * .69)
        strip_y = height * (.375 if landscape else .765)
        if hold > 0:
            # Each arc consumes exactly its share of the existing audio hold.
            # TIMER_STEPS_PER_SECOND bounds ASS size (the ring is most of a long quiz's subtitle weight).
            steps = max(1, math.ceil((tend - timer_start) * TIMER_STEPS_PER_SECOND))
            # Les 2 dernières secondes préviennent le spectateur (orange) ; pas pour un compte à rebours trop court.
            urgent_from = tend - 2 if hold >= 3 else None
            for j in range(steps):
                a = timer_start + (tend - timer_start) * j / steps
                b = timer_start + (tend - timer_start) * (j + 1) / steps
                ring(a, b, timer_x, timer_y, radius, urgent_colour if urgent_from is not None and a >= urgent_from else accent,
                     portion=max(.001, 1 - j / steps))
            for remaining in range(math.ceil(min(hold, duration)), 0, -1):
                a, b = max(timer_start, tend - remaining), tend - remaining + 1
                text(a, b, remaining, timer_x, timer_y, 62, urgent_colour if urgent_from is not None and remaining <= 2 else ink, max_width=radius * 1.5, lines=1, style="QuizTimer",
                     extra="\\fscx125\\fscy125\\t(0,160,0.4,\\fscx100\\fscy100)")
            # The full-width time strip provides peripheral timing without
            # shaking, flickering or moving the answers being read.
            rect(timer_start, tend, left, strip_y, span, 5 * scale, rail)
            rect(timer_start, tend, left, strip_y, span, 5 * scale, accent,
                 extra=f"\\fscx100\\t(0,{round((tend - timer_start) * 1000)},\\fscx0)")
    else:
        # A high-contrast answer strip opens below the cards. A brief geometric
        # burst marks the result, then settles while the explanation is spoken.
        hero_y = height * (.37 if landscape and not visual else .36)
        hero_h = height * (.105 if visual else .17 if landscape else .135)
        if visual:
            rect(start, end, left, height * .305, span, height * .115, background, layer=2)
        rect(start, end, left, hero_y - hero_h / 2, span, hero_h, accent, layer=2,
             extra="\\fscx0\\t(0,300,0.4,\\fscx100)")
        grid_h, grid_step, grid_y = question_rows(len(choices))
        source_y = (grid_y + (correct_index // 2 if question_grid else correct_index) * grid_step +
                    (grid_h / 2 if landscape else height * .045)) if focus_reveal else (
                    rows_y + correct_index * row_step + row_h / 2)
        answer = choices[correct_index] if 0 <= correct_index < len(choices) else ""
        text(start, end, answer, cx, hero_y, 78 if visual else 114, accent_ink, max_width=span - 60 * scale,
             max_height=hero_h * .80, origin=(cx, source_y), travel=min(380, round(duration * 250)),
             extra="\\fscx78\\fscy78\\t(0,380,0.4,\\fscx100\\fscy100)")
        burst_end = min(end, start + .48)
        for direction in (-1, 1):
            for j in range(3):
                x = cx + direction * (span / 2 - 12 * scale)
                y = hero_y + (j - 1) * 18 * scale
                rect(start, burst_end, x, y, 5 * scale, 5 * scale, accent,
                     origin=(cx + direction * span * .3, hero_y), travel=350, layer=3,
                     extra="\\fad(0,160)")
    return events
