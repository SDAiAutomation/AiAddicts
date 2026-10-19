"""Branchement de l'Explainer dans la chaîne de rendu (`engine/assembler.py`), style `visual_style: "explainer"`.

L'assembleur a déjà synthétisé la voix, bloc par bloc (cache d'actifs compris) : on n'y retouche pas. Ce module
transforme l'audio par bloc et les horodatages au mot en `voice_report` (le format de `timeline.narration_from_report`),
appelle `pipeline.generate` avec la narration du script (`lines` : l'Explainer ne réécrit rien), puis découpe le MP4
obtenu en un clip par bloc pour `video.render_final`. Sous-titres, mixage et musique restent ceux de la chaîne.

Aucun repli silencieux :
- un plan qui échoue à la validation est remplacé par la scène Pillow (`fallback.py`) et listé au rapport ;
- si tout l'Explainer échoue (clé manquante, Chromium absent, budget, réseau...), `ExplainerError` remonte : la
  génération échoue avec le motif, elle ne bascule pas vers un autre style.

Réglages (variables d'environnement) : `EXPLAINER_MODE` (`templates` par défaut, ou `code`), `EXPLAINER_USE_CRITIC`
(faux par défaut), `EXPLAINER_LLM_BUDGET_USD` (plafond, lu par `pipeline.generate`).
Les effets sonores de l'Explainer ne sont pas repris : seuls la voix, les sous-titres et la musique de la chaîne existante.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from . import RUNTIME_VERSION

DEFAULT_MODE = "templates"
TRUE_VALUES = {"1", "true", "yes", "on"}
SUPPORTED_ASPECT_RATIOS = {"9:16"}   # le runtime rend en 1080 x 1920 uniquement
FPS = 30


class ExplainerError(RuntimeError):
    """L'Explainer n'a pas pu produire la vidéo : la génération échoue avec ce motif, sans repli vers un autre style."""


def settings() -> dict:
    mode = (os.environ.get("EXPLAINER_MODE") or DEFAULT_MODE).strip().lower()
    use_critic = (os.environ.get("EXPLAINER_USE_CRITIC") or "").strip().lower() in TRUE_VALUES
    return {"mode": mode, "useCritic": use_critic}


def voice_report_from_blocks(blocks: list[dict], durations: list[float], block_words: list[list[dict]]) -> dict:
    """`voice_report` au format de `timeline.narration_from_report` : une ligne par bloc (texte du script) à son instant
    absolu, et les mots avec leur instant absolu. Les durées sont celles de l'audio rendu par bloc, silences ajoutés
    (pause de réflexion, maintien d'une équation) compris : le décalage de chaque bloc est la somme des précédentes."""
    if not (len(blocks) == len(durations) == len(block_words)):
        raise ExplainerError("voix : blocs, durées et mots n'ont pas le même nombre d'éléments")
    lines, words, cursor = [], [], 0.0
    for index, (block, duration, block_word_list) in enumerate(zip(blocks, durations, block_words)):
        text = str(block.get("text") or "").strip()
        if not text:
            raise ExplainerError(f"voix : le bloc {index + 1} n'a pas de texte à narrer")
        lines.append({"index": index, "start": round(cursor, 3), "text": text, "duration": round(float(duration), 3)})
        for word in block_word_list or []:
            words.append({"text": str(word["text"]), "start": round(cursor + float(word["start"]), 3),
                          "end": round(cursor + float(word["end"]), 3)})
        cursor += float(duration)
    return {"lines": lines, "words": words, "durationSeconds": round(cursor, 3), "timingSource": "measured"}


def slice_video(mp4: str | Path, durations: list[float], out_dir: str | Path) -> list[str]:
    """Un clip silencieux par bloc, à son décalage. Un clip qui dépasserait la fin de la vidéo garde sa dernière image."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths, cursor = [], 0.0
    for index, duration in enumerate(durations):
        target = out_dir / f"explainer-block-{index + 1:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{cursor:.3f}", "-i", str(mp4),
            "-vf", f"fps={FPS},tpad=stop_mode=clone:stop_duration={float(duration):.3f},format=yuv420p",
            "-t", f"{float(duration):.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(target),
        ], check=True)
        paths.append(str(target))
        cursor += float(duration)
    return paths


def summarize(report: dict) -> dict:
    """Ce que le rapport de coût du contenu garde de `explainer.report.json` (aucune valeur inconnue transformée en zéro)."""
    spend = report.get("spend") or {}
    plans = report.get("plans") or []
    fallbacks = report.get("fallbacks") or []
    steps = report.get("steps") or {}
    return {
        "mode": report.get("mode"),
        "llmCostUsd": spend.get("totalUsd"),
        "llmCostUnknown": bool(spend.get("unknownCost")),
        "llmBudgetUsd": spend.get("limitUsd"),
        "plans": len(plans),
        "fallbacks": len(fallbacks),
        "fallbackPlans": [{"plan": f.get("plan"), "reason": (f.get("reason") or [])[:2]} for f in fallbacks],
        "unresolvedAnchors": len(report.get("unresolvedAnchors") or []),
        "renderSeconds": steps.get("render"),
        "totalSeconds": steps.get("totalSeconds"),
        "stepSeconds": steps,
        "timingSource": "estimated" if report.get("timingsAreEstimated") else "measured",
        "useCritic": bool(report.get("critic")),
        "runtimeVersion": report.get("runtimeVersion", RUNTIME_VERSION),
        "chromium": (report.get("render") or {}).get("chromium"),
        "sfxIncluded": False,
        "promptVersions": report.get("promptVersions"),
    }


def _inputs_hash(lines: list[str], voice_report: dict, mode: str, use_critic: bool) -> str:
    payload = json.dumps([lines, voice_report["words"], mode, use_critic, RUNTIME_VERSION], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def generate_clips(data: dict, durations: list[float], block_words: list[list[dict]], work_dir: str | Path, *,
                   generate_fn: Callable[..., dict] | None = None, log: Callable[[str], None] = print) -> tuple[list[str], dict]:
    """Rend l'Explainer pour ce script ; renvoie (un clip par bloc, résumé pour le rapport de coût)."""
    if str(data.get("aspect_ratio") or "9:16") not in SUPPORTED_ASPECT_RATIOS:
        raise ExplainerError(f"Explainer : format 9:16 uniquement (reçu {data.get('aspect_ratio')})")
    blocks = data["blocks"]
    cfg = settings()
    if cfg["mode"] not in ("templates", "code"):
        raise ExplainerError(f"EXPLAINER_MODE inconnu : {cfg['mode']!r} (templates | code)")
    voice_report = voice_report_from_blocks(blocks, durations, block_words)
    lines = [line["text"] for line in voice_report["lines"]]
    out = Path(work_dir) / "explainer"
    out.mkdir(parents=True, exist_ok=True)
    report_path, mp4 = out / "explainer.report.json", out / "explainer.mp4"
    key = _inputs_hash(lines, voice_report, cfg["mode"], cfg["useCritic"])

    report, reused = None, False
    if mp4.exists() and mp4.stat().st_size > 0 and report_path.exists():
        try:
            stored = json.loads(report_path.read_text(encoding="utf-8"))
            if stored.get("inputsHash") == key:
                report, reused = stored, True
                log("       Explainer déjà rendu pour ces entrées — réutilisé (aucun appel LLM)")
        except (OSError, ValueError):
            report = None
    if report is None:
        if generate_fn is None:
            from . import pipeline   # import tardif : Playwright et Anthropic ne sont requis que pour ce style

            generate_fn = pipeline.generate
        try:
            report = generate_fn(str(data.get("title") or data.get("topic") or ""), out, lines=lines, voice_report=voice_report,
                                 voice_wav=None, do_render=True, use_critic=cfg["useCritic"], mode=cfg["mode"], log=log)
        except Exception as exc:  # noqa: BLE001 — remonté avec son motif, jamais remplacé par un autre style
            raise ExplainerError(f"Explainer : {type(exc).__name__}: {str(exc)[:300]}") from exc
        if report.get("timingsAreEstimated"):
            raise ExplainerError("Explainer : timings estimés alors que la voix réelle est disponible")
        report["inputsHash"] = key
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if not mp4.exists() or mp4.stat().st_size == 0:
        raise ExplainerError("Explainer : aucun MP4 produit")
    summary = summarize(report)
    summary["reused"] = reused
    return slice_video(mp4, durations, out / "blocks"), summary
