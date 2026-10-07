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
- trois modes EXPLICITES (MATH_RENDERER) :
    manim  = qualité finale : Manim + LaTeX exigés ; une dépendance manquante ou un échec lève
             MathRenderError (message exploitable, reprise possible), JAMAIS de repli silencieux ;
    auto   (défaut) : Manim s'il est installé (et LaTeX pour les équations), sinon repli Pillow,
             avec la raison enregistrée dans le rapport de rendu ;
    pillow : aperçu / rendu simplifié, jamais Manim.
- chaque clip écrit <clip>.render.json : moteur demandé / utilisé, versions, raison du repli,
  avertissements de mise en page, durées. Sans LaTeX, le texte natif de Manim (Pango) remplace
  MathTex pour les graphes seulement (les équations exigent LaTeX).

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
import time
from pathlib import Path

MANIM_SCENES = ("equation_steps", "function_graph")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FONT_DIR = _PROJECT_ROOT / "assets" / "fonts"
# Mesuré : ~60-80 s (3 étapes) à ~250 s (4 étapes + vérification) avec MiKTeX sous Windows, la composition
# LaTeX domine. 300 s était trop juste pour un poste ou un runner plus lent.
# Alertes de mise en page du rapport Manim qui font échouer le mode qualité finale.
BLOCKING_LAYOUT_NOTES = ("out_of_frame_x", "out_of_content_zone_y", "history_overlap", "history_overlaps_equation")
_TIMEOUT_SECONDS = int(os.environ.get("MANIM_TIMEOUT_SECONDS", "900") or 900)
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

class MathRenderError(Exception):
    """Échec du rendu de qualité finale (mode manim). Volontairement PAS un RuntimeError : les
    appelants qui tolèrent un visuel manquant ne doivent pas l'avaler et le remplacer par un rendu
    simplifié sans que personne ne le sache."""


_VERSION_CACHE: dict[str, str] = {}


def _first_line(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        text_out = (out.stdout or out.stderr or "").strip()
        return text_out.splitlines()[0][:120] if text_out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def versions() -> dict:
    """Versions utiles au diagnostic (mises en cache : un sous-processus par outil, une seule fois)."""
    if not _VERSION_CACHE:
        try:
            from importlib import metadata

            _VERSION_CACHE["manim"] = metadata.version("manim")
        except Exception:  # noqa: BLE001
            _VERSION_CACHE["manim"] = ""
        _VERSION_CACHE["latex"] = _first_line(["latex", "--version"]) if shutil.which("latex") else ""
        _VERSION_CACHE["ffmpeg"] = _first_line(["ffmpeg", "-version"]) if shutil.which("ffmpeg") else ""
    return dict(_VERSION_CACHE)


def dependency_report() -> dict:
    """Ce que le rendu de qualité exige, et ce qui manque (liste vide = prêt)."""
    missing = []
    if not manim_installed():
        missing.append("manim (pip install -r requirements-manim.txt)")
    if shutil.which("latex") is None:
        missing.append("latex (TeX Live / MiKTeX)")
    if shutil.which("dvisvgm") is None:
        missing.append("dvisvgm (fourni avec TeX Live / MiKTeX)")
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    return {"ok": not missing, "missing": missing, "versions": versions() if not missing else {}}


def assert_ready_for_final(scenes: list) -> None:
    """Contrôle préalable (mode manim) : échoue AVANT tout rendu si une dépendance manque."""
    if renderer_mode() != "manim" or not any(
        isinstance(s, dict) and str(s.get("sceneType") or "") in MANIM_SCENES for s in scenes
    ):
        return
    report = dependency_report()
    if not report["ok"]:
        raise MathRenderError(
            "Rendu maths de qualité finale impossible, dépendances manquantes : " + "; ".join(report["missing"])
            + ". Installer ces outils puis relancer le job (ou MATH_RENDERER=auto pour accepter le rendu simplifié)."
        )


def assert_layout_ok(layout: dict) -> None:
    """Mode manim : une alerte de mise en page bloquante (dépassement, chevauchement) lève MathRenderError.
    Les autres modes la laissent au rapport de rendu."""
    blocking = [note for note in (layout or {}).get("notes", []) if note in BLOCKING_LAYOUT_NOTES]
    if renderer_mode() == "manim" and blocking:
        raise MathRenderError("mise en page invalide dans le rendu Manim : " + ", ".join(blocking)
                              + " (raccourcir l'équation ou l'annotation, ou scinder l'étape)")


def write_render_report(out_path: str, report: dict) -> None:
    """<clip>.render.json : jamais bloquant (un rapport manquant ne doit pas perdre une vidéo)."""
    try:
        Path(str(out_path) + ".render.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def renderer_mode() -> str:
    mode = os.environ.get("MATH_RENDERER", "auto").strip().lower()
    return mode if mode in ("auto", "manim", "pillow") else "auto"


def manim_installed() -> bool:
    return importlib.util.find_spec("manim") is not None


def latex_available() -> bool:
    return shutil.which("latex") is not None and shutil.which("dvisvgm") is not None


def wants(scene: dict) -> bool:
    """True si cette scène doit être rendue par Manim (sinon rendu Pillow habituel).

    Mode manim : toujours (les dépendances manquantes sont signalées par render_clip, pas
    ignorées). Mode auto : seulement si Manim est installé, et LaTeX pour une équation, dont la
    qualité repose sur la composition LaTeX."""
    kind = str(scene.get("sceneType") or "")
    mode = renderer_mode()
    if mode == "pillow" or kind not in MANIM_SCENES:
        return False
    if mode == "manim":
        return True
    return manim_installed() and (kind != "equation_steps" or latex_available())


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
    started = time.monotonic()
    if renderer_mode() == "manim":
        deps = dependency_report()
        if not deps["ok"]:
            raise MathRenderError("dépendances manquantes : " + "; ".join(deps["missing"]))
    width, height = (int(v) for v in resolution.split("x"))
    plan = scene.get("_plan") if isinstance(scene.get("_plan"), dict) else None
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
        layout = {}
        layout_file = Path(tmp) / "layout.json"
        if layout_file.is_file():
            try:
                layout = json.loads(layout_file.read_text(encoding="utf-8"))
            except ValueError:
                layout = {}
        assert_layout_ok(layout)  # qualité finale : un dépassement réel échoue AVANT d'écrire le clip
        _fit_to_duration(produced[0], duration, fps, out)
    write_render_report(out_path, {
        "requestedEngine": renderer_mode(), "engine": "manim", "versions": versions(), "fallbackReason": None,
        "sceneType": scene.get("sceneType"), "durationSeconds": round(float(duration), 3), "fps": int(fps),
        "renderSeconds": round(time.monotonic() - started, 1), "layout": layout,
        "plan": ({"timing": plan.get("timing"), "neededDuration": plan.get("neededDuration"),
                  "warnings": plan.get("warnings", [])} if plan else None),
    })
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


def typographic_minus(content: str) -> str:
    """Poppins dessine le signe moins U+2212 comme un trait d'union court : on lui substitue le tiret
    demi-cadratin (U+2013), qui se lit comme un moins. Un trait d'union collé à un chiffre ou à une
    parenthèse (« -4 », « (-2) ») est un signe négatif ; entre deux lettres (« dix-huit ») il reste
    un trait d'union."""
    s = str(content or "").replace("\u2212", "\u2013")
    return re.sub(r"(?<![\w\u2013])-(?=[\d(])", "\u2013", s)


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
        BOLD, DOWN, ORIGIN, RIGHT, UP, Create, Dot, FadeIn, FadeOut, Line, MathTex, ReplacementTransform,
        AnimationGroup, RoundedRectangle, Scene, Succession, SurroundingRectangle, Text, VGroup, Wait, Write, config, linear,
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

    from engine.motion_graphics.display_text import display_title

    def text(s: str, color: str, bold: bool = False) -> "Text":
        kwargs = {"font": font} if font else {}
        return Text(typographic_minus(s), color=color, weight=BOLD if bold else "NORMAL", **kwargs)

    def fit(mobject, max_width: float, max_height: float):
        mobject.scale_to_fit_height(max_height)
        if mobject.width > max_width:
            mobject.scale_to_fit_width(max_width)
        return mobject

    def y_at(ratio: float) -> float:
        return frame_h / 2 - frame_h * ratio

    content_bottom = _CONTENT_BOTTOM

    class EquationSteps(Scene):
        """Équation centrale à signe « = » FIXE : l'opération apparaît, est écrite des deux côtés,
        annule ses termes, puis le résultat remplace la ligne. Tout est piloté par `_plan`
        (engine/motion_graphics/math_steps.py) ; ce code ne calcule aucun résultat mathématique."""

        def construct(self):
            from engine.motion_graphics.math_steps import build_plan, term_parts

            plan = scene_data.get("_plan") or build_plan(scene_data, None, duration)
            steps = plan["steps"]
            n = len(steps)
            rhythm = plan["rhythm"]
            tol = 1 / config.frame_rate
            eq_color, accent = theme["text"], theme["accent"]
            secondary, positive, negative = theme["secondary"], theme["positive"], theme["negative"]
            final_color = negative if plan.get("solutionKind") == "empty" else positive
            layout_notes: list[str] = []
            layout_info: list[str] = []  # informations, pas des alertes
            tracked: list = []

            def track(mobject):
                tracked.append(mobject)
                return mobject

            title = str(plan.get("title") or "")
            if title:
                head = fit(text(display_title(title), secondary, True), frame_w * 0.88, 0.5)
                head.move_to([0, y_at(_TITLE_Y), 0])
                self.add(track(head))

            def tex(strings, color):
                strings = [strings] if isinstance(strings, str) else list(strings)
                return MathTex(*strings, color=color)

            # Une seule échelle pour toute la scène : pas de changement de taille non justifié.
            candidates: list = []
            candidate_keys: list = []
            for step in steps:
                for key in ("left", "right"):
                    if step.get(key):
                        candidates.append(tex(term_parts(step[key]), eq_color))
                        candidate_keys.append(key)
                inter = step.get("intermediate")
                if inter:
                    candidates += [tex(term_parts(inter["left"]), eq_color), tex(term_parts(inter["right"]), eq_color)]
                    candidate_keys += ["left", "right"]
                if step.get("line"):
                    candidates.append(tex(step["line"], eq_color).scale(0.5))
                    candidate_keys.append("line")
            widest = max((m.width for m in candidates), default=1.0)
            tallest = max((m.height for m in candidates), default=0.5)
            # le plus large des membres + l'espace du signe « = » doit tenir dans une demi-largeur utile
            scale = min(2.2, frame_w * 0.42 / (max(widest, 1e-6) + 0.32), 1.9 / max(tallest, 1e-6))
            if scale < 1.2:
                layout_notes.append(f"small_equation_scale:{scale:.2f}")
            # Équation très asymétrique ((x − 2)(x − 3) = 0 : 2,96 à gauche, 0,21 à droite) : centrer le « = »
            # gaspille la moitié droite et force une petite échelle. Le « = » reste FIXE d'une étape à
            # l'autre mais est décalé pour équilibrer ; seulement si l'échelle serait sinon trop petite
            # (les scènes déjà validées gardent exactement leur disposition).
            eq_x = 0.0
            if scale < 1.2:
                half = frame_w * 0.42
                lefts = [m.width for m, key in zip(candidates, candidate_keys) if key == "left"]
                rights = [m.width for m, key in zip(candidates, candidate_keys) if key == "right"]
                lines = [m.width * 2 for m, key in zip(candidates, candidate_keys) if key == "line"]
                if lefts and rights:
                    balanced = min(2.2, 2 * half / (max(lefts) + max(rights) + 0.64), 1.9 / max(tallest, 1e-6),
                                   *(2 * half / w for w in lines))
                    if balanced > scale * 1.15:
                        scale = balanced
                        gap_b = 0.32 * scale
                        low = -half + max(lefts) * scale + gap_b
                        high = half - gap_b - max(rights) * scale
                        eq_x = (low + high) / 2
                        layout_info.append(f"balanced_equation:{scale:.2f}")
                        layout_notes[:] = [note_ for note_ in layout_notes if not note_.startswith("small_equation_scale")]
            gap = 0.32 * scale

            # Hauteurs : historique en haut, équation centrale, puis opération + annotation. Les lignes de
            # l'historique sont plafonnées à 0,8 unité (0,62 à quatre étapes) et espacées selon la hauteur RÉELLE de la plus haute
            # (une fraction est deux fois plus haute qu'une ligne simple : un pas fixe les faisait se chevaucher).
            def history_text(step):
                return f"{step['left']} = {step['right']}" if step.get("left") is not None else step["line"]

            history_mobs = [MathTex(history_text(step), color=secondary) for step in steps[:-1]]
            # Une seule taille pour tout l'historique (la plus contrainte : une ligne avec fraction), sinon
            # une ligne simple paraîtrait plus grosse que ses voisines.
            history_factor = min(
                (min(scale * (0.7 if n <= 3 else 0.6), (0.8 if n <= 3 else 0.62) / max(mob.height, 1e-6))
                 for mob in history_mobs), default=1.0)
            for mob in history_mobs:
                mob.scale(history_factor)
            row_units = max((m.height for m in history_mobs), default=0.0) + 0.16
            pitch = row_units / frame_h
            hist_top = 0.215 if n <= 3 else 0.205
            legacy_focal = hist_top + (0.04 if n <= 3 else 0.031) * (n - 1) + (0.085 if n <= 3 else 0.075)
            box_margin = 0.3 * scale  # le cadre du résultat final dépasse l'équation de cette marge
            # Géométrie exacte : bas de la dernière ligne d'historique + haut du cadre du résultat (équation + marge)
            last_half = (history_mobs[-1].height / 2 / frame_h) if history_mobs else 0.0
            fitted_focal = hist_top + pitch * max(n - 2, 0) + last_half + (tallest * scale / 2 + box_margin) / frame_h + 0.006
            focal = max(legacy_focal, fitted_focal)  # les scènes sans fraction gardent leur disposition d'origine
            y_focal, y_chip, y_ann = y_at(focal), y_at(focal + 0.08), y_at(focal + 0.128)
            hist_y = [y_at(hist_top + pitch * i) for i in range(len(history_mobs))]
            for mob, y in zip(history_mobs, hist_y):
                mob.move_to([0, y, 0])
            for upper, lower in zip(history_mobs, history_mobs[1:]):
                if upper.get_bottom()[1] < lower.get_top()[1]:
                    layout_notes.append("history_overlap")
            if history_mobs and history_mobs[-1].get_bottom()[1] < y_focal + tallest * scale / 2 + box_margin:
                layout_notes.append("history_overlaps_equation")

            def put_line(left, eq, right, y):
                eq.move_to([eq_x, y, 0])
                left.move_to([eq_x - (gap + left.width / 2), y, 0])
                right.move_to([eq_x + gap + right.width / 2, y, 0])

            def make_line(step, color, y, parts=True):
                """{"L","E","R","all"} ; ligne unique centrée si l'étape n'est pas une égalité simple."""
                if step.get("left") is None:
                    whole = tex(step["line"], color).scale(scale).move_to([0, y, 0])
                    return {"L": None, "E": None, "R": None, "all": whole, "line": True}
                left = tex(term_parts(step["left"]) if parts else step["left"], color).scale(scale)
                right = tex(term_parts(step["right"]) if parts else step["right"], color).scale(scale)
                eq = MathTex("=", color=color).scale(scale)
                put_line(left, eq, right, y)
                return {"L": left, "E": eq, "R": right, "all": VGroup(left, eq, right), "line": False}

            def annotation(content: str):
                if not content:
                    return None
                note_mob = fit(text(content, secondary), frame_w * 0.8, 0.42)
                return note_mob.move_to([0, y_ann, 0])

            def swap(old_mob, new_mob, total: float):
                """L'ancien état s'efface, puis le nouveau apparaît : jamais deux états superposés
                (un fondu enchaîné laisse des glyphes fantômes au milieu de la transformation)."""
                # Recouvrement de moitié : au croisement chaque état reste à ~25 % d'opacité, donc la ligne
                # n'est jamais vide (mesuré : un recouvrement de 25 % laissait 3 à 5 images sans rien).
                part = total / 1.5
                # courbe LINÉAIRE : la somme des opacités reste à 50 % pendant le recouvrement (la courbe
                # de lissage par défaut les rend toutes deux quasi invisibles au croisement)
                return AnimationGroup(FadeOut(old_mob, run_time=part, rate_func=linear),
                                      FadeIn(new_mob, run_time=part, rate_func=linear), lag_ratio=0.5)

            def wait_until(t: float):
                gap_s = t - self.renderer.time
                if gap_s > tol:
                    self.wait(gap_s)

            # --- image 1 : la première étape est déjà là ---------------------------------------
            cur = make_line(steps[0], eq_color, y_focal)
            note = annotation(steps[0].get("annotation", ""))
            self.add(track(cur["all"]))
            if note is not None:
                self.add(track(note))

            for k in range(1, n):
                step, ev = steps[k], steps[k]["events"]
                prev = steps[k - 1]
                op = step.get("operation") or {}
                kind = op.get("kind")
                inter = step.get("intermediate")
                writable = bool(inter) and kind in ("add", "mul", "div") and not cur["line"]

                # 1. l'opération est nommée : étiquette + annotation courte
                wait_until(ev["showOp"])
                new_note = annotation(step.get("annotation", ""))
                label = None
                anims = []
                if writable:
                    label = track(MathTex(op["tex"], color=accent).scale(scale * 0.85).move_to([eq_x, y_chip, 0]))
                    anims.append(FadeIn(label, scale=0.8))
                if new_note is not None:
                    track(new_note)
                    anims.append(swap(note, new_note, max(rhythm["op_in"], 0.2)) if note is not None
                                 else FadeIn(new_note, shift=DOWN * 0.12))
                elif note is not None:
                    anims.append(FadeOut(note))
                if anims:
                    self.play(*anims, run_time=max(rhythm["op_in"], 0.2))
                note = new_note if new_note is not None else note

                # 2. « aux deux membres » : l'opération est écrite de chaque côté
                chips = None
                if writable:
                    wait_until(ev["sides"])
                    sides_time = max(rhythm["sides_move"], 0.25)
                    if kind == "add":
                        m = len(term_parts(prev["left"]))
                        mr = len(term_parts(prev["right"]))
                        left_i = tex(term_parts(inter["left"])[:m] + ["{}" + op["tex"]], eq_color).scale(scale)
                        right_i = tex(term_parts(inter["right"])[:mr] + ["{}" + op["tex"]], eq_color).scale(scale)
                        left_i.move_to([eq_x - (gap + left_i.width / 2), y_focal, 0])
                        right_i.move_to([eq_x + gap + right_i.width / 2, y_focal, 0])
                        track(left_i), track(right_i)
                        chip_l, chip_r = label.copy(), label.copy()
                        self.add(chip_l, chip_r)
                        # Translation pure (même glyphes, même échelle) : aucune forme intermédiaire déformée.
                        grow = scale / (scale * 0.85)
                        def chip_motion(chip, target_group, base_index, base_tex):
                            """Le terme s'aligne sur la ligne de base des chiffres voisins ; derrière une fraction,
                            sur sa barre (le bas de la fraction est le bas du dénominateur, pas la ligne)."""
                            end = target_group[len(target_group) - 1].get_center()
                            motion = chip.animate.scale(grow)
                            if r"\frac" in base_tex:
                                return motion.move_to([end[0], target_group[base_index].get_center()[1], 0])
                            return motion.move_to(end).align_to(target_group[base_index], DOWN)

                        self.play(
                            cur["L"].animate.move_to(VGroup(*[left_i[i] for i in range(m)]).get_center()),
                            cur["R"].animate.move_to(VGroup(*[right_i[i] for i in range(mr)]).get_center()),
                            chip_motion(chip_l, left_i, m - 1, term_parts(prev["left"])[m - 1]),
                            chip_motion(chip_r, right_i, mr - 1, term_parts(prev["right"])[mr - 1]),
                            FadeOut(label), run_time=sides_time,
                        )
                        chips = (chip_l, chip_r)
                    else:
                        left_i = tex(inter["left"], eq_color).scale(scale)
                        right_i = tex(inter["right"], eq_color).scale(scale)
                        left_i.move_to([eq_x - (gap + left_i.width / 2), y_focal, 0])
                        right_i.move_to([eq_x + gap + right_i.width / 2, y_focal, 0])
                        track(left_i), track(right_i)
                        self.play(swap(VGroup(cur["L"], cur["R"], label), VGroup(left_i, right_i), sides_time), run_time=sides_time)
                        cur["L"], cur["R"] = left_i, right_i

                # 3. le résultat : annulation, simplification, trace dans l'historique
                wait_until(ev["apply"])
                last = k == n - 1
                result_color = final_color if last else eq_color
                # Termes séparés même après une réécriture : l'étape suivante peut annuler un terme par son rang
                after = make_line(step, result_color, y_focal, parts=True)
                track(after["all"])
                history = history_mobs[k - 1] if k - 1 < len(history_mobs) else None
                if history is not None:
                    track(history)
                # Tout ce qui suit tient dans apply_anim : le plan (math_steps) compte exactement ce budget.
                apply_total = max(rhythm["apply_anim"], 0.4)
                box = None
                if last and not after["line"]:
                    box = track(SurroundingRectangle(after["all"], color=final_color, buff=0.3 * scale,
                                                     corner_radius=0.2, stroke_width=5))
                anims = []
                if cur["line"] or after["line"]:
                    anims.append(swap(cur["all"], after["all"], apply_total))
                else:
                    if chips is not None:  # addition/soustraction : les termes opposés s'annulent
                        cancel = step.get("cancel") or {}
                        tint = []
                        for side_key, side_mob, chip in (("left", cur["L"], chips[0]), ("right", cur["R"], chips[1])):
                            index = cancel.get(side_key)
                            if index is not None:
                                tint += [side_mob[index].animate.set_color(negative), chip.animate.set_color(negative)]
                        if tint:
                            pre = min(0.25, apply_total * 0.3)
                            self.play(*tint, run_time=pre)
                            apply_total = max(apply_total - pre, 0.3)
                        for side_key, side_mob, chip, target in (
                            ("left", cur["L"], chips[0], after["L"]), ("right", cur["R"], chips[1], after["R"]),
                        ):
                            index = cancel.get(side_key)
                            if index is not None:
                                keep = VGroup(*[side_mob[i] for i in range(len(side_mob)) if i != index])
                                anims += [FadeOut(VGroup(side_mob[index], chip), scale=0.6, run_time=apply_total),
                                          ReplacementTransform(keep, target, run_time=apply_total)]
                            else:
                                anims.append(swap(VGroup(side_mob, chip), target, apply_total))
                    else:
                        anims.append(swap(VGroup(cur["L"], cur["R"]), VGroup(after["L"], after["R"]), apply_total))
                    # le signe « = » reste en place (même objet) : seuls les membres changent. Le groupe `all`
                    # doit le contenir, sinon une transition suivante (vers une ligne « x = 2 ou x = 3 »)
                    # laisserait ce « = » à l'écran sous la nouvelle ligne.
                    after["E"] = cur["E"]
                    after["all"] = VGroup(after["L"], after["E"], after["R"])
                    if last:
                        anims.append(cur["E"].animate.set_color(final_color))
                if history is not None:
                    anims.append(FadeIn(history, shift=UP * 0.12, run_time=apply_total))
                if box is not None:
                    anims.append(Succession(Wait(apply_total * 0.55), Create(box, run_time=apply_total * 0.45)))
                self.play(*anims, run_time=apply_total)
                cur = after

            # --- vérification par substitution (si le plan en contient une) ---------------------
            verification = plan.get("verification")
            if verification:
                wait_until(verification["at"])
                sub = verification["substitution"]
                label_v = fit(text(verification["label"], secondary, True), frame_w * 0.5, 0.42)
                has_frac = r"\frac" in (sub["left"] + sub["right"] + sub["leftValue"] + sub["rightValue"])
                label_v.move_to([0, y_at(focal + (0.105 if has_frac else 0.115)), 0])
                bare = re.fullmatch(r"-?\d+", sub["right"].replace(" ", "")) is not None
                tick = MathTex(r"\checkmark", color=positive)
                if bare:
                    first = VGroup(MathTex(sub["left"], "=", sub["leftValue"], color=eq_color), tick).arrange(RIGHT, buff=0.35)
                    second = None
                else:
                    first = MathTex(sub["left"], "=", sub["right"], color=eq_color)
                    second = VGroup(MathTex(sub["leftValue"], "=", sub["rightValue"], color=eq_color), tick).arrange(RIGHT, buff=0.35)
                row_cap = 0.95 if has_frac else (0.8 if bare else 0.6)
                fit(first, frame_w * 0.84, row_cap).move_to(
                    [0, y_at(focal + ((0.17 if has_frac else 0.168) if bare else 0.158)), 0])
                track(label_v), track(first)
                reveal = [FadeIn(label_v, shift=DOWN * 0.1), Write(first[0] if bare else first)]
                if note is not None:
                    self.play(FadeOut(note), run_time=0.2)
                self.play(*reveal, run_time=max(rhythm["verify_anim"] * 0.6, 0.4))
                if bare:
                    self.play(FadeIn(tick, scale=0.5), run_time=max(rhythm["verify_anim"] * 0.3, 0.3))
                else:
                    fit(second, frame_w * 0.84, 0.6).move_to([0, y_at(focal + 0.2), 0])
                    track(second)
                    self.play(FadeIn(second, shift=DOWN * 0.1), run_time=max(rhythm["verify_anim"] * 0.4, 0.3))

            # --- garde-fous de mise en page (rapport, pas de correction silencieuse) ------------
            top_limit, bottom_limit = y_at(0.12), y_at(content_bottom + 0.005)
            for mobject in tracked:
                try:
                    if mobject.get_left()[0] < -frame_w / 2 * 0.97 or mobject.get_right()[0] > frame_w / 2 * 0.97:
                        layout_notes.append("out_of_frame_x")
                    if mobject.get_top()[1] > top_limit + 1e-6 or mobject.get_bottom()[1] < bottom_limit - 1e-6:
                        layout_notes.append("out_of_content_zone_y")
                except Exception:  # noqa: BLE001 — la mesure est un contrôle, jamais bloquante
                    pass
            self.layout_report = {
                "equationScale": round(scale, 3),
                "equationHeightPx": round(tallest * scale * height_px / frame_h, 1),
                "notes": sorted(set(layout_notes)),
                "info": layout_info,
                # Objets VISIBLES restant à l'écran en fin de scène (les fondus laissent des conteneurs vides,
                # ignorés ici) : un reste oublié d'une étape précédente, par exemple un « = » sous la ligne
                # « x = 2 ou x = 3 », augmente ce nombre.
                "visibleOnScreen": sum(1 for m in self.mobjects if any(sm.has_points() for sm in m.get_family())),
            }
            remaining = duration - self.renderer.time
            if remaining > tol:
                self.wait(remaining)

    class FunctionGraph(Scene):
        def construct(self):
            slope, intercept = float(scene_data["slope"]), float(scene_data["intercept"])
            x_min, x_max = float(scene_data.get("xMin", -5)), float(scene_data.get("xMax", 5))
            y_min, y_max = float(scene_data.get("yMin", -5)), float(scene_data.get("yMax", 5))
            title = str(scene_data.get("title") or "")
            if title:
                head = fit(text(display_title(title), theme["secondary"], True), frame_w * 0.88, 0.5)
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
        scene = scene_class()
        scene.render()
        report = getattr(scene, "layout_report", None)
        if report is not None:
            (Path(media_dir) / "layout.json").write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    _main(sys.argv[1], sys.argv[2])
