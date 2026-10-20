"""Vertical (9:16) chapter exports of a five-level 50-question quiz.

A Short is NOT a crop of the 16:9 master. Each chapter is re-composed from the same compiled blocks and the
same already-synthesized narration, through the portrait Motion layout (`quiz_motion.scene_events` is authored
for 1080x1920): large type, stacked answer cards, a ring timer in the lower third, captions above the platform
controls, a per-chapter progress bar. No voice is re-synthesized (zero provider cost) and the audio of a block is
byte-for-byte the master's, so narration, countdown sound effects and visuals stay synchronized by construction.

Duration policy. YouTube Shorts accept up to 3 minutes (verify against YouTube's help centre before changing
`SHORT_MAX_SECONDS`). A chapter whose MEASURED duration exceeds the limit is never sped up or truncated: it is
split at a question boundary into the fewest balanced parts (`quiz_easy_part1.mp4`, ...), each opening with the
chapter card. Every output records its measured duration and `short_eligible`.

Failure policy. Chapters render independently, each in a private temp folder and published with an atomic
rename only after ffprobe validation; one failure never touches the master video or the other chapters.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Callable

from . import captions, quiz_motion, tts, video

SHORT_MAX_SECONDS = 180.0
SHORT_MARGIN_SECONDS = 2.0  # keep clear of the limit: container rounding must never tip a Short over
SHORT_RESOLUTION = (1080, 1920)
CHAPTER_STEMS = {1: "quiz_easy", 2: "quiz_medium", 3: "quiz_hard", 4: "quiz_expert", 5: "quiz_genius"}
DURATION_TOLERANCE_SECONDS = 0.25


class ExportError(RuntimeError):
    """A chapter export that must be reported as failed (message is safe to show to the user)."""


def audio_path(work_dir: Path, index: int, block: dict) -> Path:
    """Audio file the master render used for block `index` (1-based). Mirrors assembler._synthesize_block."""
    name = f"block-{index:02d}-padded.mp3" if float(block.get("hold_after_seconds") or 0) > 0 else f"block-{index:02d}.mp3"
    return Path(work_dir) / "audio" / name


def ensure_padded_audio(block: dict, raw_path: Path, padded_path: Path) -> Path:
    """Narration + silent reflection window (with countdown ticks) for a block with `hold_after_seconds`.

    Single source of truth shared by the master render (engine/assembler.py) and the chapter exports, so both
    produce the same audio from the same narration."""
    padded_path = Path(padded_path)
    if padded_path.exists() and padded_path.stat().st_size > 0:
        return padded_path
    hold = float(block.get("hold_after_seconds") or 0)
    beat = float(block.get("quiz_reveal_beat_seconds") or 0) if hold > 0 else 0.0
    mode = str(block.get("quiz_sound_effects") or "off")
    if mode != "off":
        video.add_countdown_sfx(str(raw_path), tts.get_duration_seconds(str(raw_path)), int(hold), str(padded_path),
                                mode, str(block.get("quiz_theme") or "studio"), beat)
    else:
        video.pad_audio(str(raw_path), hold + beat, str(padded_path))
    return padded_path


def _chapter_blocks(data: dict) -> dict[int, list[int]]:
    """Master block indices (0-based) per chapter: card first, then its question/reveal pairs."""
    chapters: dict[int, list[int]] = {n: [] for n in range(1, 6)}
    for index, block in enumerate(data.get("blocks") or []):
        phase = block.get("quiz_phase")
        if phase == "chapter":
            chapters[int(block["quiz_chapter_number"])].append(index)
        elif phase in {"question", "reveal"}:
            chapters[int(block["quiz_chapter_number"] if phase == "question" else
                         (int(block["quiz_question_number"]) - 1) // 10 + 1)].append(index)
    return chapters


def require_exportable(data: dict) -> None:
    quiz = data.get("quiz") or {}
    if data.get("content_format") != "quiz" or quiz.get("chapter_mode") != "five_levels":
        raise ExportError("Seuls les quiz 50 questions en cinq niveaux peuvent être exportés par chapitre.")
    if quiz.get("presentation") != "motion":
        raise ExportError("L'export par chapitre exige la présentation Motion.")
    chapters = _chapter_blocks(data)
    if any(len(v) != 21 for v in chapters.values()):
        raise ExportError("Le script ne contient pas cinq chapitres complets ; recompile le quiz.")


def partition(units: list[float], lead: float, limit: float) -> list[tuple[int, int]]:
    """Split question units (seconds) into the fewest contiguous parts of lead+sum <= limit, balanced (min-max).

    Returns [(first_unit, last_unit_exclusive)]. Raises when even one unit cannot fit."""
    if not units:
        raise ExportError("Chapitre vide.")
    if lead + max(units) > limit:
        raise ExportError("Une seule question dépasse la durée maximale d'un Short.")
    n = len(units)
    prefix = [0.0]
    for unit in units:
        prefix.append(prefix[-1] + unit)
    for parts in range(1, n + 1):
        # DP: best[k][i] = minimal achievable max part length using k parts over first i units.
        inf = float("inf")
        best = [[inf] * (n + 1) for _ in range(parts + 1)]
        cut = [[0] * (n + 1) for _ in range(parts + 1)]
        best[0][0] = 0.0
        for k in range(1, parts + 1):
            for i in range(1, n + 1):
                for j in range(k - 1, i):
                    length = lead + prefix[i] - prefix[j]
                    value = max(best[k - 1][j], length)
                    if value < best[k][i]:
                        best[k][i], cut[k][i] = value, j
        if best[parts][n] <= limit:
            spans, i = [], n
            for k in range(parts, 0, -1):
                spans.append((cut[k][i], i))
                i = cut[k][i]
            return spans[::-1]
    raise ExportError("Impossible de découper le chapitre sous la durée maximale.")


def plan_exports(data: dict, durations: list[float], limit: float = SHORT_MAX_SECONDS) -> list[dict]:
    """One plan per output file, from MEASURED block durations (same order as data['blocks'])."""
    require_exportable(data)
    blocks = data["blocks"]
    if len(durations) != len(blocks):
        raise ExportError("Durées audio mesurées manquantes.")
    plans = []
    for chapter, indices in _chapter_blocks(data).items():
        card, pairs = indices[0], indices[1:]
        lead = durations[card]
        units = [durations[pairs[i]] + durations[pairs[i + 1]] for i in range(0, len(pairs), 2)]
        spans = partition(units, lead, limit - SHORT_MARGIN_SECONDS)
        for part, (a, b) in enumerate(spans, 1):
            chosen = [card, *pairs[a * 2:b * 2]]
            stem = CHAPTER_STEMS[chapter] + (f"_part{part}" if len(spans) > 1 else "")
            total = sum(durations[i] for i in chosen)
            plans.append({
                "chapter": chapter, "label": quiz_motion_label(chapter), "part": part, "parts": len(spans),
                "file": f"{stem}.mp4", "blocks": chosen,
                "first_question": a + 1 + (chapter - 1) * 10, "last_question": b + (chapter - 1) * 10,
                "expected_duration": round(total, 3), "short_eligible": total <= limit,
            })
    return plans


def quiz_motion_label(chapter: int) -> str:
    from .quiz import CHAPTER_LABELS
    return CHAPTER_LABELS[chapter - 1]


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60)
    info = json.loads(result.stdout)
    streams = info.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {"width": video_stream.get("width"), "height": video_stream.get("height"),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "duration": float(info.get("format", {}).get("duration") or 0)}


def validate_output(path: Path, expected_duration: float) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        raise ExportError("Le fichier exporté est vide.")
    info = probe(path)
    if (info["width"], info["height"]) != SHORT_RESOLUTION:
        raise ExportError(f"Résolution inattendue : {info['width']}x{info['height']}.")
    if not info["has_audio"]:
        raise ExportError("Le fichier exporté n'a pas de piste audio.")
    if abs(info["duration"] - expected_duration) > DURATION_TOLERANCE_SECONDS:
        raise ExportError(f"Durée mesurée {info['duration']:.2f}s au lieu de {expected_duration:.2f}s : audio et image désynchronisés.")
    return info


def _portrait_blocks(data: dict, plan: dict) -> list[dict]:
    """Copies of the chapter blocks prepared for the vertical composition."""
    blocks = [deepcopy(data["blocks"][i]) for i in plan["blocks"]]
    for block in blocks:
        block["quiz_visual_available"] = False  # text-only vertical layout: no 16:9 illustration window
        block["quiz_layout"] = "short"
        block.pop("quiz_base_background", None)
        if block.get("quiz_phase") == "chapter":
            block["quiz_first_question"], block["quiz_last_question"] = plan["first_question"], plan["last_question"]
        elif block.get("quiz_phase") in {"question", "reveal"}:
            block["quiz_view_first"], block["quiz_view_last"] = plan["first_question"], plan["last_question"]
    return blocks


def _safe_message(exc: Exception, root: Path) -> str:
    message = str(exc) if isinstance(exc, ExportError) else "Le rendu du chapitre a échoué."
    return message.replace(str(root), "…")[:300]


def render_plan(data: dict, work_dir: Path, plan: dict, out_dir: Path) -> dict:
    """Render one output file. Raises ExportError (user-safe) on any problem; nothing is published on failure."""
    work_dir, out_dir = Path(work_dir).resolve(), Path(out_dir).resolve()
    if out_dir != work_dir and work_dir not in out_dir.parents:
        raise ExportError("Dossier d'export hors de l'espace de travail.")
    final = out_dir / plan["file"]
    if final.parent != out_dir or final.name != Path(plan["file"]).name:
        raise ExportError("Nom de fichier d'export invalide.")
    tmp = out_dir / f".{final.stem}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        blocks = _portrait_blocks(data, plan)
        audio_files, durations, block_words = [], [], []
        for src_index, block in zip(plan["blocks"], blocks):
            path = audio_path(work_dir, src_index + 1, data["blocks"][src_index])
            if not path.is_file() or path.stat().st_size == 0:
                raise ExportError("Audio du chapitre introuvable : régénère d'abord la vidéo complète.")
            duration = tts.get_playback_duration_seconds(str(path))
            words_file = path.parent / f"block-{src_index + 1:02d}.words.json"
            words = json.loads(words_file.read_text(encoding="utf-8")) if words_file.is_file() else []
            audio_files.append(str(path))
            durations.append(duration)
            block_words.append((words, duration))
        quiz_motion.build_timeline({**data, "blocks": blocks}, durations)  # same sanity checks as the master
        audio = video.concat_audio(audio_files, str(tmp / "audio.wav"))
        cues = captions.build_cues(block_words, block_roles=[str(b.get("role") or "") for b in blocks])
        backgrounds = [quiz_motion.base_background_for(data, 0.0, b) for b in blocks]
        for block, colour in zip(blocks, backgrounds):
            if colour:
                block["quiz_base_background"] = "#" + colour[2:].lower()
        font = quiz_motion.BRAND_FONT if not os.environ.get("SUBTITLE_FONT") and quiz_motion.brand_font_available() else None
        resolution = f"{SHORT_RESOLUTION[0]}x{SHORT_RESOLUTION[1]}"
        ass = captions.write_ass(cues, str(tmp / "captions.ass"), captions.caption_style_or_default(data.get("caption_style")),
                                 resolution, blocks=blocks, block_durations=durations, font=font)
        rendered = tmp / "out.mp4"
        video.render_final(audio, ass, str(rendered), durations, image_paths=None, aspect_ratio="9:16",
                           bg_colors=backgrounds if any(backgrounds) else None,
                           **({"fonts_dir": str(quiz_motion.FONT_DIR)} if font else {}))
        info = validate_output(rendered, sum(durations))
        out_dir.mkdir(parents=True, exist_ok=True)
        os.replace(rendered, final)  # atomic publish: readers never see a partial file
        return {**{k: plan[k] for k in ("chapter", "label", "part", "parts", "file", "first_question", "last_question")},
                "status": "ready", "duration": round(info["duration"], 3),
                "width": info["width"], "height": info["height"], "bytes": final.stat().st_size,
                "short_eligible": info["duration"] <= SHORT_MAX_SECONDS, "error": None}
    except ExportError:
        raise
    except Exception as exc:  # ffmpeg/ffprobe/IO: details stay in the worker log, not in the user-facing error
        print(f"       export {plan['file']} : {type(exc).__name__}: {exc}")
        raise ExportError("Le rendu du chapitre a échoué.") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def export_chapters(data: dict, work_dir: str | Path, out_dir: str | Path | None = None, chapters: list[int] | None = None,
                    on_progress: Callable[[str], None] | None = None) -> dict:
    """Render the requested chapters (default: all five). Returns a manifest; failed chapters never raise."""
    work_dir = Path(work_dir).resolve()
    out_dir = Path(out_dir).resolve() if out_dir else work_dir / "shorts"
    requested = sorted(set(chapters or range(1, 6)))
    if any(isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= 5 for c in requested):
        raise ExportError("Chapitre invalide (1 à 5).")
    durations = []
    for index, block in enumerate(data.get("blocks") or [], 1):
        path = audio_path(work_dir, index, block)
        if not path.is_file():
            raise ExportError("Audio du master introuvable : régénère d'abord la vidéo complète.")
        durations.append(tts.get_playback_duration_seconds(str(path)))
    plans = [p for p in plan_exports(data, durations) if p["chapter"] in requested]
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for plan in plans:
        if on_progress:
            on_progress(f"Short {plan['label']} ({plan['part']}/{plan['parts']})")
        try:
            items.append(render_plan(data, work_dir, plan, out_dir))
        except ExportError as exc:
            items.append({**{k: plan[k] for k in ("chapter", "label", "part", "parts", "file", "first_question", "last_question")},
                          "status": "failed", "error": _safe_message(exc, work_dir)})
    manifest = {"version": 1, "limitSeconds": SHORT_MAX_SECONDS, "items": items}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
