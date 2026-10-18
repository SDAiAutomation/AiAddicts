"""Opt-in quiz choreography on the existing libass/FFmpeg timeline.

No provider calls, generated code, new renderer or additional audio track.
All timings are relative to the measured narration block. Choices settle
before the existing silent reflection period; answer data is only used in
the reveal. Text is escaped and fitted with the classic renderer's helpers.
"""
from __future__ import annotations

import math

VERSION = "quiz-motion:v3"

# Anneau du compte à rebours : 70 % du poids des sous-titres d'un quiz long (mesuré avec
# scripts/measure_quiz_motion.py). 12 images/s et 48 points suffisent à l'œil pour un anneau de 100 px.
TIMER_STEPS_PER_SECOND = 12
RING_POINTS = 48


_LIGHT_THEMES = {"minimal", "logo"}


def stage_background(theme: str | None) -> str:
    """Couleur de la scène Motion (#rrggbb) ; les thèmes clairs ont une scène claire."""
    return "#eef2f6" if theme in _LIGHT_THEMES else "#080e1c"


def base_background_for(script: dict, fade_duration: float) -> str | None:
    """Couleur FFmpeg (`0xRRGGBB`) à donner au fond uni de la vidéo, ou None.

    Dessiner la scène en rectangle plein écran dans libass coûte un mélange 1080p par image :
    mesuré à ~60 % du temps de rendu d'un quiz long. Quand la vidéo de base est déjà de la
    couleur de la scène, le rectangle devient inutile. Pas de fondu au noir entre les plans :
    il serait visible sans le rectangle qui le recouvrait."""
    info = presentation_info(script)
    if info is None or info["mode"] != "motion" or fade_duration > 0:
        return None
    return "0x" + stage_background((script.get("quiz") or {}).get("theme"))[1:].upper()


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
        if not math.isfinite(hold) or hold < 0 or hold > duration:
            raise ValueError(f"Quiz : la durée audio du bloc {index + 1} ne contient pas son temps de réflexion.")
        scene = {"block": index, "phase": block.get("quiz_phase"),
                 "startSeconds": round(cursor, 4), "endSeconds": round(cursor + duration, 4)}
        if block.get("quiz_phase") == "question":
            scene["reflectionStartSeconds"] = round(cursor + duration - hold, 4)
            scene["reflectionSeconds"] = hold
            scene["entranceEnabled"] = info["mode"] == "motion" and duration - hold >= 1
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


def scene_events(block: dict, start: float, end: float, width: int, height: int) -> list[str]:
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
    background = stage_background(block.get("quiz_theme"))
    rail = "#cbd5e1" if light else "#243249"
    events: list[str] = []

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

    def text(a, b, value, x, y, size, colour, *, max_width=span, max_height=None, lines=2, origin=None, delay=0, travel=420, extra="", style="QuizQuestion", layer=3):
        fs, content = _quiz_fit_text(str(value), round(max_width), max(1, round(size * scale)), lines)
        if max_height is not None:
            fitted = min(fs, max(1, int(max_height / ((content.count(r"\N") + 1) * 1.25))))
            fs, content = _quiz_fit_text(str(value), round(max_width), fitted, lines)
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

    # Preserve the illustration as a real window; never substitute invented
    # factual diagrams for a supplied image/logo question.
    visual = bool(block.get("quiz_visual_available")) and phase in {"question", "reveal"}
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
    for x, direction in ((left, 1), (right, -1)):
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
        text(start, end, "QUIZ" if phase == "intro" else "✓", cx, height * .30, 216, ink,
             lines=1, origin=(cx - span * .12, height * .30), travel=settle,
             extra=f"\\fscx112\\t(0,{settle},0.4,\\fscx100)")
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
    animate = phase == "question" and duration - hold >= 1.0
    correct_index = int(block.get("quiz_correct_choice") or 0) if phase == "reveal" else -1
    # Offsets follow the type size in landscape, where `span` is far wider than
    # the glyphs and fractions of it would push "/ 03" away from "01".
    number_x, total_x = (left + 80 * scale, left + 160 * scale) if landscape else (left + span * .09, left + span * .17)
    text(start, end, f"{number:02d}", number_x, height * .145, 74, ink, lines=1, max_width=span * .18)
    text(start, end, f"/ {total:02d}", total_x, height * .15, 30, accent, lines=1, max_width=span * .13)
    gap = 7 * scale
    segment = (span * .46 - (total - 1) * gap) / total
    for i in range(total):
        rect(start, end, right - span * .46 + i * (segment + gap), height * .146,
             segment, 7 * scale, accent if i < number else rail)

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
            return ((height * .15, height * .17, height * .405) if question_grid else
                    (height * (.105 if count == 4 else .12), height * (.12 if count == 4 else .135), height * .40))
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
            rows_y, row_h, row_step = height * .50, height * .05, height * .058
    question_y = height * (.224 if visual else .225 if focus_reveal else .277)
    text(start, end, block.get("quiz_question", ""), cx, question_y, 64 if visual else 46 if focus_reveal else 76,
         ink, lines=3, max_height=height * (.09 if focus_reveal else .105 if visual else .17),
         # En paysage le compte à rebours occupe la droite de la ligne de la question.
         max_width=span - 2 * 154 * scale if landscape and phase == "question" else span,
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
        # A shallow offset shadow gives each answer physical presence.
        rect(start, end, x + 5 * scale, y + 6 * scale, card_w, row_h, rail,
             origin=(origin[0] + 5 * scale, origin[1] + 6 * scale) if origin else None,
             delay=delay, travel=travel, extra=fold)
        rect(start, end, x, y, card_w, row_h, fill, origin=origin, delay=delay, travel=travel, extra=fold)
        rect(start, end, x, y, max(3, 5 * scale), row_h, accent if not selected else selected_ink,
             origin=origin, delay=delay, travel=travel)
        label_x, label_y = x + (30 if grid else 35) * scale, y + row_h * (.23 if grid else .5)
        label_origin = (label_x, label_y + height * .055) if origin else None
        if focus_reveal:
            label_origin = (old_x + (30 if question_grid else 35) * scale,
                            old_y + old_row_h * (.23 if question_grid else .5))
        text(start, end, "✓" if selected else "ABCD"[i], label_x, label_y, 26 if grid or (landscape and focus_reveal) else 34,
             selected_ink if selected else accent, max_width=52 * scale, lines=1,
             origin=label_origin, delay=delay, travel=travel)
        answer_x = x + card_w / 2 + (0 if grid else 22 * scale)
        answer_y = y + row_h * (.61 if grid else .5)
        answer_origin = (answer_x, answer_y + height * .055) if origin else None
        if focus_reveal:
            answer_origin = (old_x + old_card_w / 2 + (0 if question_grid else 22 * scale),
                             old_y + old_row_h * (.61 if question_grid else .5))
        text(start, end, choice, answer_x, answer_y, 43 if grid else 44,
             selected_ink if selected else ink, max_width=card_w - (44 if grid else 150) * scale,
             max_height=row_h * (.52 if grid else .86),
             origin=answer_origin, delay=delay, travel=travel,
             style="QuizCorrect" if selected else "QuizChoice")

    if phase == "question":
        timer_start = max(start, end - hold)
        radius = 57 * scale
        # Portrait : sous les réponses. Paysage : à droite de la question (les réponses occupent la hauteur),
        # avec le trait de temps juste sous elle.
        timer_x, timer_y = (right - radius - 6 * scale, height * .277) if landscape else (cx, height * .69)
        strip_y = height * (.375 if landscape else .765)
        if hold > 0:
            # Each arc consumes exactly its share of the existing audio hold.
            # TIMER_STEPS_PER_SECOND bounds ASS size (the ring is most of a long quiz's subtitle weight).
            steps = max(1, math.ceil((end - timer_start) * TIMER_STEPS_PER_SECOND))
            for j in range(steps):
                a = timer_start + (end - timer_start) * j / steps
                b = timer_start + (end - timer_start) * (j + 1) / steps
                ring(a, b, timer_x, timer_y, radius, accent, portion=max(.001, 1 - j / steps))
            for remaining in range(math.ceil(min(hold, duration)), 0, -1):
                a, b = max(timer_start, end - remaining), min(end, end - remaining + 1)
                text(a, b, remaining, timer_x, timer_y, 62, ink, max_width=radius * 1.5, lines=1, style="QuizTimer",
                     extra="\\fscx125\\fscy125\\t(0,160,0.4,\\fscx100\\fscy100)")
            # The full-width time strip provides peripheral timing without
            # shaking, flickering or moving the answers being read.
            rect(timer_start, end, left, strip_y, span, 5 * scale, rail)
            rect(timer_start, end, left, strip_y, span, 5 * scale, accent,
                 extra=f"\\fscx100\\t(0,{round((end - timer_start) * 1000)},\\fscx0)")
    else:
        # A high-contrast answer strip opens below the cards. A brief geometric
        # burst marks the result, then settles while the explanation is spoken.
        hero_y = height * .36
        hero_h = height * (.105 if visual else .135)
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
