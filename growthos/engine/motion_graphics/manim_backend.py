"""Rendu Manim (la bibliothèque de 3Blue1Brown) des scènes maths `equation_steps` et `function_graph`.

Même contrat que le rendu Pillow (`renderer.render_scene_clip`) : un `.mp4` muet à la durée EXACTE
du bloc, révélations calées sur la voix (`_reveals` posé par `sync.py`), mêmes couleurs de thème,
même zone de sécurité (ni la bande sous-titres du bas, ni l'interface de la plateforme en haut).
Ce que Manim apporte : l'équation se TRANSFORME d'une étape à la suivante (les morceaux communs
glissent, les morceaux nouveaux arrivent) au lieu d'apparaître dans un nouveau cadre, et les
formules sont composées par LaTeX.

Garde-fous (jamais bloquant, comme tout le reste de `motion_graphics`) :
- le rendu tourne dans un SOUS-PROCESSUS avec délai maximal : un blocage ou un plantage de Manim
  ne touche pas le worker ;
- toute erreur remonte en exception et `render_scene_clip` retombe sur le rendu Pillow ;
- `MATH_RENDERER=pillow` désactive Manim ; `auto` (défaut) l'utilise s'il est installé ;
  `manim` le demande explicitement. Sans LaTeX, le texte natif de Manim (Pango) remplace `MathTex`.

Aucune vérification mathématique ici : le contrôle reste `math_validation.py`, avant ce rendu.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MANIM_SCENES = ("equation_steps", "function_graph")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FONT_DIR = _PROJECT_ROOT / "assets" / "fonts"
_TIMEOUT_SECONDS = int(os.environ.get("MANIM_TIMEOUT_SECONDS", "300") or 300)
_CRF = "19"
_DIM_OPACITY = 0.55  # une étape déjà lue s'efface un peu quand la suivante arrive

# Mêmes proportions que le rendu Pillow (scenes.render_equation_steps / render_function_graph).
_TITLE_Y = 0.14
_STACK_TOP = 0.185
_FORMULA_Y = 0.205
_LABEL_Y = 0.267
_GRAPH_TOP = 0.29
_TICK_GAP = 0.04
_CONTENT_BOTTOM = 0.58  # 1 - layout.CAPTION_RESERVED_RATIO (canvas.SAFE_BOTTOM_RATIO = 0.42)


# ---------------------------------------------------------------------------
# Côté worker : choix du moteur et lancement du sous-processus
# ---------------------------------------------------------------------------

def renderer_mode() -> str:
    mode = os.environ.get("MATH_RENDERER", "auto").strip().lower()
    return mode if mode in ("auto", "manim", "pillow") else "auto"


def manim_installed() -> bool:
    return importlib.util.find_spec("manim") is not None


def latex_available() -> bool:
    return shutil.which("latex") is not None and shutil.which("dvisvgm") is not None


def wants(scene: dict) -> bool:
    """True si cette scène doit être rendue par Manim (sinon rendu Pillow habituel)."""
    return (
        renderer_mode() != "pillow"
        and str(scene.get("sceneType") or "") in MANIM_SCENES
        and manim_installed()
    )


def _fit_to_duration(raw: Path, duration: float, fps: int, out_path: Path) -> None:
    """Coupe ou prolonge (dernière image figée) le clip Manim à la durée exacte du bloc."""
    tmp_out = out_path.with_suffix(".tmp.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(raw),
        "-vf", f"tpad=stop_mode=clone:stop_duration=3,fps={fps},format=yuv420p",
        "-t", f"{max(duration, 0.1):.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", _CRF, "-an", str(tmp_out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", "") or str(exc)).strip().splitlines()[-5:]
        raise RuntimeError("ajustement de la durée du clip Manim échoué : " + " | ".join(detail)) from exc
    tmp_out.replace(out_path)


def render_clip(scene: dict, duration: float, out_path: str, resolution: str, fps: int, theme) -> str:
    """Rend `scene` avec Manim vers `out_path` (durée exacte). Lève RuntimeError au moindre échec."""
    width, height = (int(v) for v in resolution.split("x"))
    job = {
        "scene": {k: v for k, v in scene.items() if not str(k).startswith("__")},
        "duration": float(duration),
        "size": [width, height],
        "fps": int(fps),
        "theme": dataclasses.asdict(theme),
        "tex": latex_available(),
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="manim-job-") as tmp:
        job_path = Path(tmp) / "job.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "engine.motion_graphics.manim_backend", str(job_path), tmp],
                cwd=str(_PROJECT_ROOT), capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Manim a dépassé {_TIMEOUT_SECONDS}s") from exc
        if proc.returncode != 0:
            tail = " | ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-6:])
            raise RuntimeError(f"Manim a échoué (code {proc.returncode}) : {tail}")
        produced = sorted(
            p for p in Path(tmp).rglob("scene.mp4") if "partial_movie_files" not in p.parts
        )
        if not produced:
            raise RuntimeError("Manim n'a produit aucun fichier vidéo")
        _fit_to_duration(produced[0], duration, fps, out)
    return out_path


# ---------------------------------------------------------------------------
# Fonctions pures (testées sans Manim)
# ---------------------------------------------------------------------------

def tex_tokens(equation: str) -> list[str]:
    """Une égalité découpée comme `scenes._equation_tokens` (espaces), chaque jeton prêt pour LaTeX."""
    s = str(equation or "").replace("−", "-").replace("×", r"\times").replace("÷", r"\div").replace("²", "^2")
    s = re.sub(r"(?<=\d)\*(?=x)", "", s).replace("*", r"\cdot")
    s = re.sub(r"\bou\b", r"\\text{ou}", s, flags=re.I)
    return s.split()


def line_segment(slope: float, intercept: float, x_min: float, x_max: float,
                 y_min: float, y_max: float) -> tuple[float, float] | None:
    """Intervalle de x où la droite reste dans la fenêtre, ou None si elle n'y passe pas."""
    if slope == 0:
        return (x_min, x_max) if y_min <= intercept <= y_max else None
    a, b = (y_min - intercept) / slope, (y_max - intercept) / slope
    lo, hi = max(x_min, min(a, b)), min(x_max, max(a, b))
    return (lo, hi) if lo < hi else None


def reveal_times(scene: dict, count: int, duration: float) -> list[float]:
    """Instant (secondes) d'arrivée de chaque étape : voix si `_reveals`, sinon rythme régulier."""
    reveals = scene.get("_reveals")
    if reveals and len(reveals) >= count:
        times = [max(0.0, float(r)) * duration for r in reveals[:count]]
    else:
        times = [duration * (0.04 + 0.68 * i / max(count, 1)) for i in range(count)]
    times[0] = 0.0  # jamais d'image vide : la première étape est là dès l'image 1
    for i in range(1, count):
        times[i] = max(times[i], times[i - 1] + 0.35)
    return times


def coefficient_text(value: float) -> str:
    if value == 1:
        return ""
    if value == -1:
        return "-"
    return f"{value:g}"


def graph_formula(slope: float, intercept: float) -> str:
    sign = "+" if intercept >= 0 else "-"
    tail = f" {sign} {abs(intercept):g}" if intercept else ""
    return f"y = {coefficient_text(slope)}x{tail}" if slope else f"y = {intercept:g}"


# ---------------------------------------------------------------------------
# Côté sous-processus : la scène Manim elle-même
# ---------------------------------------------------------------------------

def _register_fonts() -> str:
    """Poppins fourni avec le dépôt (même police que le rendu Pillow) ; police système sinon."""
    try:
        import manimpango

        ok = [manimpango.register_font(str(_FONT_DIR / name)) for name in ("Poppins-Regular.ttf", "Poppins-Bold.ttf")]
        return "Poppins" if all(ok) else ""
    except Exception:  # noqa: BLE001 — la police est cosmétique
        return ""


def _build(job: dict):
    from manim import (
        BOLD, DOWN, ORIGIN, Create, Dot, FadeIn, Line, MathTex, RoundedRectangle, Scene, Text, TransformMatchingShapes,
        TransformMatchingTex, VGroup, config,
    )
    import numpy as np

    theme = job["theme"]
    scene_data = job["scene"]
    duration = float(job["duration"])
    use_tex = bool(job["tex"])
    font = _register_fonts()
    width_px, height_px = job["size"]
    frame_h = 16.0
    frame_w = frame_h * width_px / height_px

    def text(s: str, color: str, bold: bool = False) -> "Text":
        kwargs = {"font": font} if font else {}
        return Text(s, color=color, weight=BOLD if bold else "NORMAL", **kwargs)

    def fit(mobject, max_width: float, max_height: float):
        mobject.scale_to_fit_height(max_height)
        if mobject.width > max_width:
            mobject.scale_to_fit_width(max_width)
        return mobject

    def y_at(ratio: float) -> float:
        return frame_h / 2 - frame_h * ratio

    content_bottom = _CONTENT_BOTTOM

    class EquationSteps(Scene):
        def construct(self):
            from engine.motion_graphics.scenes import _changed_flags

            steps = (scene_data.get("steps") or [])[:4]
            n = len(steps)
            title = str(scene_data.get("title") or "")
            if title:
                head = fit(text(title.upper(), theme["secondary"], True), frame_w * 0.88, 0.5)
                head.move_to([0, y_at(_TITLE_Y), 0])
                self.add(head)
            top = y_at(_STACK_TOP)
            bottom = y_at(content_bottom - 0.02)
            avail = top - bottom
            row_h = min(avail / n, frame_h * 0.17)
            gap = row_h * 0.12
            panel_h = row_h - gap
            start = top - (avail - row_h * n) / 2
            solution_kind = scene_data.get("_solutionKind")
            final_color = theme["negative"] if solution_kind == "empty" else theme["positive"]
            times = reveal_times(scene_data, n, duration)

            panels, equations, captions = [], [], []
            for i, step in enumerate(steps):
                panel_top = start - i * row_h
                cy = panel_top - panel_h / 2
                panel = RoundedRectangle(
                    width=frame_w * 0.86, height=panel_h, corner_radius=0.22,
                    fill_color=theme["primary"], fill_opacity=0.09, stroke_width=0,
                ).move_to([0, cy, 0])
                last = i == n - 1
                color = final_color if last else theme["text"]
                equation = str(step.get("equation") or "")
                explanation = str(step.get("explanation") or "")
                if use_tex:
                    tokens = tex_tokens(equation)
                    mob = MathTex(*tokens, color=color)
                    if i > 0 and not last:
                        flags = _changed_flags(str(steps[i - 1].get("equation") or ""), equation)
                        if len(flags) == len(mob) and any(flags):
                            for k, flagged in enumerate(flags):
                                if flagged:
                                    mob[k].set_color(theme["accent"])
                else:
                    mob = text(equation, color, True)
                fit(mob, frame_w * 0.78, panel_h * 0.38)
                mob.move_to([0, panel_top - panel_h * (0.40 if explanation else 0.50), 0])
                caption = None
                if explanation:
                    caption = fit(text(explanation, theme["secondary"]), frame_w * 0.78, 0.42)
                    caption.move_to([0, panel_top - panel_h * 0.80, 0])
                panels.append(panel)
                equations.append(mob)
                captions.append(caption)

            # frame 1 : la première étape est déjà à l'écran
            self.add(panels[0], equations[0])
            if captions[0] is not None:
                self.add(captions[0])
            for i in range(1, n):
                gap_s = times[i] - self.renderer.time
                if gap_s > 1 / config.frame_rate:
                    self.wait(gap_s)
                budget = (times[i + 1] - times[i]) if i + 1 < n else max(duration - times[i], 0.3)
                run = min(0.9, max(0.3, budget * 0.6))
                morph = (TransformMatchingTex if use_tex else TransformMatchingShapes)(equations[i - 1].copy(), equations[i])
                animations = [FadeIn(panels[i]), morph, equations[i - 1].animate.set_opacity(_DIM_OPACITY)]
                if captions[i] is not None:
                    animations.append(FadeIn(captions[i], shift=DOWN * 0.15))
                self.play(*animations, run_time=run)
            remaining = duration - self.renderer.time
            if remaining > 1 / config.frame_rate:
                self.wait(remaining)

    class FunctionGraph(Scene):
        def construct(self):
            slope, intercept = float(scene_data["slope"]), float(scene_data["intercept"])
            x_min, x_max = float(scene_data.get("xMin", -5)), float(scene_data.get("xMax", 5))
            y_min, y_max = float(scene_data.get("yMin", -5)), float(scene_data.get("yMax", 5))
            title = str(scene_data.get("title") or "")
            if title:
                head = fit(text(title.upper(), theme["secondary"], True), frame_w * 0.88, 0.5)
                head.move_to([0, y_at(_TITLE_Y), 0])
                self.add(head)
            formula_str = graph_formula(slope, intercept)
            if use_tex:
                formula = MathTex(formula_str.replace("-", "-"), color=theme["text"])
            else:
                formula = text(formula_str, theme["text"], True)
            fit(formula, frame_w * 0.78, 0.9).move_to([0, y_at(_FORMULA_Y), 0])
            self.add(formula)

            x0, x1 = -frame_w * 0.36, frame_w * 0.36
            y_top, y_bot = y_at(_GRAPH_TOP), y_at(content_bottom - _TICK_GAP)

            def P(x: float, y: float):
                return np.array([
                    x0 + (x - x_min) / (x_max - x_min) * (x1 - x0),
                    y_bot + (y - y_min) / (y_max - y_min) * (y_top - y_bot),
                    0.0,
                ])

            grid = VGroup()
            for k in range(int(np.ceil(x_min)), int(np.floor(x_max)) + 1):
                grid.add(Line(P(k, y_min), P(k, y_max), stroke_width=1.5, color=theme["secondary"], stroke_opacity=0.22))
            for k in range(int(np.ceil(y_min)), int(np.floor(y_max)) + 1):
                grid.add(Line(P(x_min, k), P(x_max, k), stroke_width=1.5, color=theme["secondary"], stroke_opacity=0.22))
            axes = VGroup()
            if x_min <= 0 <= x_max:
                axes.add(Line(P(0, y_min), P(0, y_max), stroke_width=4, color=theme["secondary"], stroke_opacity=0.75))
            if y_min <= 0 <= y_max:
                axes.add(Line(P(x_min, 0), P(x_max, 0), stroke_width=4, color=theme["secondary"], stroke_opacity=0.75))
            box = RoundedRectangle(
                width=x1 - x0, height=y_top - y_bot, corner_radius=0.02, stroke_width=3,
                stroke_color=theme["secondary"], stroke_opacity=0.75, fill_opacity=0,
            ).move_to([(x0 + x1) / 2, (y_top + y_bot) / 2, 0])
            labels = VGroup()
            for value, pos in ((x_min, (x0, y_bot - 0.45)), (x_max, (x1, y_bot - 0.45)),
                               (y_max, (x0 + 0.5, y_top - 0.35)), (y_min, (x0 + 0.5, y_bot + 0.35))):
                labels.add(fit(text(f"{value:g}", theme["secondary"]), 1.4, 0.42).move_to([pos[0], pos[1], 0]))
            self.add(grid, axes, box, labels)

            segment = line_segment(slope, intercept, x_min, x_max, y_min, y_max)
            if segment is not None:
                line = Line(P(segment[0], slope * segment[0] + intercept), P(segment[1], slope * segment[1] + intercept),
                            stroke_width=8, color=theme["primary"])
                self.wait(min(0.15 * duration, 0.5))
                self.play(Create(line), run_time=max(0.4, duration * 0.5))
            if "highlightX" in scene_data:
                hx = float(scene_data["highlightX"])
                hy = slope * hx + intercept
                dot = Dot(P(hx, hy), radius=0.2, color=theme["accent"])
                caption = fit(text(f"x = {hx:g}   y = {hy:g}", theme["accent"]), frame_w * 0.78, 0.5)
                caption.move_to([0, y_at(_LABEL_Y - 0.004), 0])
                self.play(FadeIn(dot, scale=0.4), FadeIn(caption), run_time=min(0.6, max(0.3, duration * 0.12)))
            remaining = duration - self.renderer.time
            if remaining > 1 / config.frame_rate:
                self.wait(remaining)

    return EquationSteps if scene_data.get("sceneType") == "equation_steps" else FunctionGraph


def _main(job_path: str, media_dir: str) -> None:
    from manim import tempconfig

    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    width_px, height_px = job["size"]
    settings = {
        "pixel_width": width_px, "pixel_height": height_px, "frame_rate": job["fps"],
        "frame_height": 16.0, "frame_width": 16.0 * width_px / height_px,
        "background_color": job["theme"]["background"], "media_dir": media_dir,
        "disable_caching": True, "verbosity": "ERROR", "progress_bar": "none",
        "output_file": "scene", "write_to_movie": True, "format": "mp4",
    }
    with tempconfig(settings):
        scene_class = _build(job)
        scene_class().render()


if __name__ == "__main__":
    _main(sys.argv[1], sys.argv[2])
