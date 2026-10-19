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
Les bruitages de l'Explainer sont mixés sous la voix par `mix_sfx` (étape audio de l'assembleur) ; sans piste audio dans le MP4, le rapport l'écrit (`sfxIncluded: false`).
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


# Niveau des bruitages sous la voix. Mesuré (voix simulée à niveau de parole) : l'ancien réglage de `render.audio_args`
# (gain 0,8, seuil 0,03, ratio 10) laissait les pics des bruitages ~17 dB sous ceux de la voix, soit inaudibles ; ce réglage
# les place ~4 dB sous. Valeurs à confirmer à l'oreille avec la vraie voix : réglables par variables d'environnement.
SFX_DEFAULTS = {"gain": 1.6, "duck_threshold": 0.06, "duck_ratio": 4.0}
SFX_ENV = {"gain": "EXPLAINER_SFX_GAIN", "duck_threshold": "EXPLAINER_SFX_DUCK_THRESHOLD", "duck_ratio": "EXPLAINER_SFX_DUCK_RATIO"}
SFX_LIMITS = {"gain": (0.1, 4.0), "duck_threshold": (0.001, 1.0), "duck_ratio": (1.0, 20.0)}


def sfx_mix_settings() -> dict:
    """Réglage du mixage des bruitages (défauts ci-dessus, surchargés par EXPLAINER_SFX_*). Une valeur invalide lève
    `ExplainerError` : jamais d'ignorance silencieuse d'un réglage."""
    settings_ = {}
    for key, default in SFX_DEFAULTS.items():
        raw = (os.environ.get(SFX_ENV[key]) or "").strip()
        try:
            value = float(raw) if raw else default
        except ValueError:
            raise ExplainerError(f"{SFX_ENV[key]} invalide : {raw!r} (nombre attendu)") from None
        low, high = SFX_LIMITS[key]
        if not low <= value <= high:
            raise ExplainerError(f"{SFX_ENV[key]} hors limites : {value} (entre {low} et {high})")
        settings_[key] = value
    return settings_


def mix_sfx(voice_audio: str | Path, mp4: str | Path, out_wav: str | Path) -> str | None:
    """Mixe les bruitages de l'Explainer (piste audio du MP4, aucune voix dedans) sous la voix de la chaîne : bruitages
    baissés quand la voix parle (sidechain), puis mixés (réglage : `sfx_mix_settings`). Renvoie le WAV mixé, ou None si le MP4
    n'a pas de piste audio (le rapport le dit : `sfxIncluded: false`)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(mp4)],
                           capture_output=True, text=True, check=True)
    if not probe.stdout.strip():
        return None
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    mix = sfx_mix_settings()
    graph = (f"[0:a]asplit=2[vk][vm];[1:a]volume={mix['gain']}[sfx];"
             f"[sfx][vk]sidechaincompress=threshold={mix['duck_threshold']}:ratio={mix['duck_ratio']}:attack=5:release=350[duck];"
             "[duck][vm]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice_audio), "-i", str(mp4), "-filter_complex", graph,
                    "-map", "[mix]", "-ar", "48000", "-ac", "2", str(out)], check=True)
    return str(out)


def summarize(report: dict) -> dict:
    """Ce que le rapport de coût du contenu garde de `explainer.report.json` (aucune valeur inconnue transformée en zéro)."""
    spend = report.get("spend") or {}
    calls = spend.get("calls") or []
    def token_total(key: str) -> int | None:
        values = [call.get(key) for call in calls]
        return sum(values) if values and all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values) else None

    input_tokens = token_total("inputTokens")
    output_tokens = token_total("outputTokens")
    cache_read_tokens = token_total("cacheReadTokens")
    cache_write_tokens = token_total("cacheWriteTokens")
    denominator = None if any(v is None for v in (input_tokens, cache_read_tokens, cache_write_tokens)) else input_tokens + cache_read_tokens + cache_write_tokens
    plans = report.get("plans") or []
    fallbacks = report.get("fallbacks") or []
    steps = report.get("steps") or {}
    return {
        "mode": report.get("mode"),
        "llmCostUsd": spend.get("totalUsd"),
        "llmCostUnknown": bool(spend.get("unknownCost")),
        "llmBudgetUsd": spend.get("limitUsd"),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheReadTokens": cache_read_tokens,
        "cacheWriteTokens": cache_write_tokens,
        "costByStepUsd": spend.get("byStep"),
        "cacheReadRate": cache_read_tokens / denominator if denominator else None,
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
        "sfxIncluded": False,   # passe à True quand `mix_sfx` a mixé les bruitages (voir assembler)
        "promptVersions": report.get("promptVersions"),
    }


def _inputs_hash(lines: list[str], voice_report: dict, mode: str, use_critic: bool, language: str = "fr") -> str:
    payload = json.dumps([lines, voice_report["words"], mode, use_critic, RUNTIME_VERSION, language], ensure_ascii=False, sort_keys=True)
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
    language = str(data.get("language") or "fr").strip().lower()
    key = _inputs_hash(lines, voice_report, cfg["mode"], cfg["useCritic"], language)

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
            try:
                from . import pipeline   # import tardif : Playwright, Anthropic et esprima ne sont requis que pour ce style
            except ImportError as exc:
                raise ExplainerError(
                    f"Explainer : dépendances non installées ({exc.name or exc}). L'étape « Installer Chromium et les dépendances "
                    "Explainer » du worker a été ignorée (contenu non détecté en file) : relancer la génération, ou définir la variable "
                    "de dépôt EXPLAINER_ALWAYS_INSTALL = true."
                ) from exc

            generate_fn = pipeline.generate
        try:
            report = generate_fn(str(data.get("title") or data.get("topic") or ""), out, lines=lines, voice_report=voice_report,
                                 voice_wav=None, do_render=True, use_critic=cfg["useCritic"], mode=cfg["mode"], language=language, log=log)
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
    summary["video"] = str(mp4)
    return slice_video(mp4, durations, out / "blocks"), summary
