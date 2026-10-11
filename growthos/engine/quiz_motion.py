"""Opt-in quiz choreography on the existing libass/FFmpeg timeline.

No provider calls, generated code, new renderer or additional audio track.
All timings are relative to the measured narration block. Choices settle
before the existing silent reflection period; answer data is only used in
the reveal. Text is escaped and fitted with the classic renderer's helpers.
"""
from __future__ import annotations

import math

VERSION = "quiz-motion:v1"


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
    scale = min(width / 1080, height / 1920)
    cx = width / 2
    left, right = width * .08, width * .90
    span = right - left
    # Theme remains independent of presentation. Light themes use a light stage.
    card, ink, correct, accent = _QUIZ_THEME_COLOURS.get(block.get("quiz_theme"), _QUIZ_THEME_COLOURS["studio"])
    channels = [int(correct[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    luminance = sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    selected_ink = "#000000" if luminance > .179 else "#ffffff"
    light = block.get("quiz_theme") in {"minimal", "logo"}
    background = "#eef2f6" if light else "#080e1c"
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

    def text(a, b, value, x, y, size, colour, *, max_width=span, max_height=None, lines=2, origin=None, delay=0, travel=420, extra="", style="QuizQuestion"):
        fs, content = _quiz_fit_text(str(value), round(max_width), max(1, round(size * scale)), lines)
        if max_height is not None:
            fitted = min(fs, max(1, int(max_height / ((content.count(r"\N") + 1) * 1.25))))
            fs, content = _quiz_fit_text(str(value), round(max_width), fitted, lines)
        tags = f"\\an5{position(x,y,origin,delay,travel)}\\fs{fs}\\bord0\\shad0\\b1\\q2\\1c{_ass_rgb(colour)}{extra}"
        emit(a, b, tags, content, 3, style)

    def ring(a, b, x, y, radius, colour, extra="", portion=1.0):
        # Filled polygonal annulus: deterministic vectors, no font dependency.
        outer, inner = radius, max(1, radius - max(2, 4 * scale))
        count = max(3, round(64 * portion))
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
    else:
        rect(start, end, 0, 0, width, height, background, layer=0)

    # Vertical spine persists across acts, giving the viewer a spatial anchor.
    rect(start, end, left, height * .12, max(2, 3 * scale), height * .53, rail)
    if phase in {"intro", "outro"}:
        title = block.get("quiz_topic") or "QUIZ"
        number = "?" if phase == "intro" else "✓"
        settle = min(700, round(duration * 350))
        ring(start, end, cx, height * .31, 115 * scale, accent,
             f"\\fscx45\\fscy45\\t(0,{settle},\\fscx100\\fscy100)")
        text(start, end, number, cx, height * .31, 124, ink,
             extra=f"\\fscx65\\fscy65\\t(0,{settle},\\fscx100\\fscy100)")
        text(start, end, title, cx, height * .49, 98, ink, lines=3,
             origin=(cx, height * .54), travel=settle)
        rect(start, end, cx - span * .15, height * .605, span * .30, max(3, 7 * scale), accent,
             extra=f"\\fscx0\\t(0,{settle},\\fscx100)")
        return events

    choices = [str(c) for c in block.get("quiz_choices") or []]
    number = int(block.get("quiz_question_number") or 1)
    total = max(number, int(block.get("quiz_question_total") or number))
    text(start, end, f"{number:02d} / {total:02d}", cx, height * .135, 34, accent, lines=1)
    rect(start, end, left, height * .164, span, max(2, 3 * scale), rail)
    rect(start, end, left, height * .164, span * number / total, max(2, 3 * scale), accent)
    text(start, end, block.get("quiz_question", ""), cx, height * .223, 64, ink, lines=3, max_height=height * .105)

    # Four visual-answer rows must end above the two-line caption band.
    row_h = height * (.040 if visual else .046)
    row_step = height * (.048 if visual else .054)
    rows_y = height * (.455 if visual else .345)
    hold = max(0.0, float(block.get("hold_after_seconds") or 0))
    # Reserve 200 ms fully settled before the measured reflection window.
    animate = phase == "question" and duration - hold >= 1.0
    correct_index = int(block.get("quiz_correct_choice") or 0) if phase == "reveal" else -1
    for i, choice in enumerate(choices):
        y = rows_y + i * row_step
        selected = i == correct_index
        delay, travel = i * 75, 440
        origin = (cx - span * .5, height * .37) if animate else None
        # The answer rails expand out of a shared visual anchor into their
        # final rows; the text travels with its card, then remains motionless.
        x = left + 14 * scale
        fill = correct if selected else card
        rect(start, end, x, y, span - 14 * scale, row_h, fill, origin=origin, delay=delay, travel=travel)
        rect(start, end, x, y, max(3, 5 * scale), row_h, accent if not selected else ink,
             origin=origin, delay=delay, travel=travel)
        label_origin = (origin[0] + 32 * scale, origin[1] + row_h / 2) if origin else None
        text(start, end, "✓" if selected else "ABCD"[i], x + 32 * scale, y + row_h / 2, 34,
             selected_ink if selected else accent, max_width=64 * scale, lines=1,
             origin=label_origin, delay=delay, travel=travel)
        answer_origin = (cx + 22 * scale, origin[1] + row_h / 2) if origin else None
        text(start, end, choice, cx + 22 * scale, y + row_h / 2, 44,
             selected_ink if selected else ink, max_width=span - 150 * scale, max_height=row_h * .86,
             origin=answer_origin, delay=delay, travel=travel,
             style="QuizCorrect" if selected else "QuizChoice")

    if phase == "question":
        timer_start = max(start, end - hold)
        timer_y = height * (.71 if visual else .615)
        radius = 35 * scale
        if hold > 0:
            # Each arc consumes exactly its share of the existing audio hold.
            # 24 steps/second is enough for the small timer and bounds ASS size.
            steps = max(1, math.ceil((end - timer_start) * 24))
            for j in range(steps):
                a = timer_start + (end - timer_start) * j / steps
                b = timer_start + (end - timer_start) * (j + 1) / steps
                ring(a, b, cx, timer_y, radius, accent, portion=max(.001, 1 - j / steps))
            for remaining in range(math.ceil(min(hold, duration)), 0, -1):
                a, b = max(timer_start, end - remaining), min(end, end - remaining + 1)
                text(a, b, remaining, cx, timer_y, 35, ink, max_width=radius * 1.5, lines=1, style="QuizTimer")
    else:
        # Reveal grows from the selected row into a distinct answer headline.
        # Keep the original rows visible so viewers can still locate their pick.
        hero_y = height * (.36 if visual else .62)
        if visual:
            rect(start, end, left, height * .305, span, height * .115, background, layer=2)
        source_y = rows_y + correct_index * row_step + row_h / 2
        answer = choices[correct_index] if 0 <= correct_index < len(choices) else ""
        text(start, end, answer, cx, hero_y, 64, accent, max_width=span - 70 * scale,
             max_height=height * .075,
             origin=(cx, source_y), travel=min(550, round(duration * 300)),
             extra="\\fscx70\\fscy70\\t(0,450,\\fscx100\\fscy100)")
    return events
