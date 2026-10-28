"""Storyboard renderer for animated stories: one illustrated still per 2-4 s beat, animated by the editor (camera moves,
hard cuts, grain), with the narration and dialogue of the measured timeline and burned captions in the Standard presets.

Why: the puppet renderer (rig_v1) showed two characters standing in the same pose for ~7 s per shot. The reference videos
(docs/product/STORY_STUDIO_GATE0_REFERENCE_ANALYSIS_2026-10-24.md) cut on every idea, show what the narration says (actions,
inserts, metaphor objects with faces) and keep 1-3 recurring characters strictly identical. This renderer reuses the
Standard building blocks instead of a new system: the image client and model router, the style and character bibles, the
scene prompt builder, the Ken Burns clips of `engine/video.py` and the caption presets of `engine/captions.py`.

Pure helpers (prompts, costs, beat moves) are separated from the IO (`render`), and every paid operation is a port injected
by the caller: the pipeline reserves the credit before calling `render`, and tests never touch a provider.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import captions, image_character_bible, image_model_router, image_prompt_builder, image_style_bible, video
from . import beats as beats_lib, direction as direction_lib, quality as quality_lib
from .renderer import CostEstimate, RenderError, RenderResult

STORYBOARD = "storyboard"
RIG_V1 = "rig_v1"
RENDERERS = (STORYBOARD, RIG_V1)
DEFAULT_RENDERER = STORYBOARD
VERSION = "storyboard/1.0.0"

WIDTH, HEIGHT, FPS = 1080, 1920, 25
RESOLUTION = f"{WIDTH}x{HEIGHT}"
AVG_BEAT_S = 2.5            # images paid for = video seconds / this (beats are 2-4 s; the cap is enforced after the split)
MAX_BEATS = 90              # hard ceiling whatever the duration (200 s / 2.2 s)
RETRY_SHARE = 0.2           # extra image calls allowed for retries, as a share of the image cap (at least 2)
IMAGE_ATTEMPTS = 2          # per beat, on top of the client's own transient retries
FINAL_CRF = "28"            # final pass: grain is expensive to encode (crf 21 measured ~4 MiB/s); 28 as rig_v1, ~0.25 MiB/s
FADE_S = 0.12               # fade to and from black at a section change (kept short: no visible black)
MAX_REUSED_SHARE = 0.3      # above this share of reused pictures, the clip goes to human review
IMAGE_CALL_SECONDS = 14.0   # the image client spaces calls by 13 s (5 images/minute)
ENCODE_RATIO_ESTIMATE = 3.0  # wall-clock / video seconds for clips + final pass (supersampled Ken Burns), estimate only
DEFAULT_SERVER_MAX_USD = 8.0
FALLBACK_USD_PER_IMAGE = 0.08
# output tokens of one portrait (1024x1536) image per quality, used only to ESTIMATE before the call
_PORTRAIT_OUTPUT_TOKENS = {"low": 400, "medium": 1584, "high": 6240, "auto": 1584}
_PROMPT_INPUT_TOKENS = 900
CAMERA_TO_KB = {"push_in": "in", "pull_out": "out", "pan_left": "left", "pan_right": "right", "static": "in_slow",
                "shake": "shake"}
_REUSE_MOVES = ("up", "right", "out", "left", "in")
_VIDEO_EXTS = (".mp4", ".mov", ".webm", ".m4v")

# Built-in look of the recurring characters of the approved packs (used when the script carries no description).
PACK_LOOKS = {
    "pip_v1": ("un petit homme cartoon rubber hose à grosse tête ronde toute blanche, petites lunettes rondes, moustache "
               "noire en brosse, chapeau melon noir, nœud papillon rouge, gants blancs, costume sombre"),
    "rosette_v1": ("une dame cartoon rubber hose au visage rond et expressif, chapeau noir orné d'une fleur rouge, robe "
                   "sombre à col blanc, gants blancs, petit sac à main"),
}
GENERIC_LOOK = "un personnage cartoon rubber hose reconnaissable, silhouette et tenue identiques dans chaque plan"


def renderer_from_env(env: dict | None = None) -> str:
    """`STORY_RENDERER` = storyboard | rig_v1 (default storyboard). An unknown value falls back to the default, loudly."""
    raw = ((env if env is not None else os.environ).get("STORY_RENDERER") or "").strip().lower()
    if not raw:
        return DEFAULT_RENDERER
    if raw not in RENDERERS:
        print(f"       STORY_RENDERER={raw!r} inconnu : rendu {DEFAULT_RENDERER} utilisé")
        return DEFAULT_RENDERER
    return raw


def server_max_usd() -> float:
    try:
        value = float(os.environ.get("STORY_STORYBOARD_MAX_USD", "") or DEFAULT_SERVER_MAX_USD)
    except ValueError:
        return DEFAULT_SERVER_MAX_USD
    return value if math.isfinite(value) and value > 0 else DEFAULT_SERVER_MAX_USD


def usd_per_image_estimate() -> float:
    """Estimated $ for one final portrait image with the model the router selects: token prices from the environment
    when configured (as the Standard pipeline), else the historical table, else a conservative fallback. Never 0."""
    sel = image_model_router.select_model("final")
    usage = {"input_text": _PROMPT_INPUT_TOKENS, "input_image": 0, "output": _PORTRAIT_OUTPUT_TOKENS.get(sel.quality, 1584)}
    cost = image_model_router.estimate_cost(sel.model, sel.quality, usage)
    if cost and cost > 0:
        return round(cost, 4)
    try:
        return float(os.environ.get("STORY_IMAGE_USD_FALLBACK", "") or FALLBACK_USD_PER_IMAGE)
    except ValueError:
        return FALLBACK_USD_PER_IMAGE


# ---------------------------------------------------------------- ports and cost plan

@dataclass
class StoryboardPorts:
    generate_image: Callable[[str, Path], object]          # (prompt, out path) -> path or None; may raise (caught)
    call_llm: Callable | None = None                       # (messages, model) -> (text, usage); None = deterministic direction
    llm_model: str | None = None
    usd_per_image: float = FALLBACK_USD_PER_IMAGE          # estimate only, never an invoice
    llm_reserve_usd: float = 0.05                          # estimated upper cost of one direction call
    # Seam for a later image-to-video provider: (beat, direction, image path, seconds, workdir) -> clip path or None.
    # Nothing implements it here; its cost must be declared in `key_clip_usd` before it is enabled.
    key_clip: Callable | None = None
    max_key_clips: int = 0
    key_clip_usd: float = 0.0
    image_attempts: int = IMAGE_ATTEMPTS
    max_usd: float = DEFAULT_SERVER_MAX_USD                # server-side cap, on top of the story's own budget
    fps: int = FPS


@dataclass(frozen=True)
class CostPlan:
    max_images: int          # beats are merged down to this number after the split
    image_calls: int         # max paid image calls (cap + retries)
    llm_calls: int
    images_usd: float
    llm_usd: float
    key_clips_usd: float

    @property
    def extra_usd(self) -> float:
        return round(self.images_usd + self.llm_usd + self.key_clips_usd, 4)


def plan_costs(video_seconds: float, ports: StoryboardPorts) -> CostPlan:
    """Upper bound of what the storyboard adds to the voices, computed BEFORE the credit is reserved."""
    max_images = max(1, min(MAX_BEATS, math.ceil(video_seconds / AVG_BEAT_S)))
    image_calls = max_images + max(2, math.ceil(RETRY_SHARE * max_images))
    llm_calls = direction_lib.MAX_ATTEMPTS if (ports.call_llm and ports.llm_model) else 0
    clips = max(0, int(ports.max_key_clips)) if ports.key_clip else 0
    return CostPlan(max_images, image_calls, llm_calls, round(image_calls * ports.usd_per_image, 4),
                    round(llm_calls * ports.llm_reserve_usd, 4), round(clips * ports.key_clip_usd, 4))


def estimate(video_seconds: float, tts_chars: int, ports: StoryboardPorts) -> CostEstimate:
    plan = plan_costs(video_seconds, ports)
    render_s = plan.max_images * IMAGE_CALL_SECONDS + video_seconds * ENCODE_RATIO_ESTIMATE
    return CostEstimate(render_seconds=round(render_s, 1), tts_chars=tts_chars,
                        provider_calls=plan.image_calls + plan.llm_calls)


# ---------------------------------------------------------------- prompts (pure)

def character_looks(story: dict, script: dict | None = None) -> dict:
    """character id -> {"name", "description"} for the recurring characters. A Standard-shaped `script["characters"]`
    entry ({id or name, description}) wins; otherwise the pack's built-in look."""
    authored = {}
    for entry in (script or {}).get("characters") or []:
        if isinstance(entry, dict):
            desc = direction_lib.clean_text(entry.get("description"), 300)
            for key in (entry.get("id"), entry.get("name")):
                if isinstance(key, str) and desc:
                    authored.setdefault(key, desc)
    looks = {}
    for c in story.get("characters") or []:
        desc = authored.get(c["id"]) or authored.get(c["name"]) or PACK_LOOKS.get(c.get("pack_id")) or GENERIC_LOOK
        looks[c["id"]] = {"name": c["name"], "description": desc}
    return looks


def beat_prompt(direction: dict, style_bible: dict, looks: dict) -> str:
    """Image prompt of one beat: the direction (what to show), the story's style bible and the identity of the recurring
    characters present in that beat only (others are not mentioned, so the model does not add them)."""
    present = [{"name": looks[c]["name"], "description": looks[c]["description"]}
               for c in direction.get("characters", []) if c in looks]
    prefix = image_character_bible.build_character_prefix(present, None)
    texts = [direction["show"]]
    crowd = [direction_lib.CROWD_TYPES[c] for c in direction.get("crowd", []) if c in direction_lib.CROWD_TYPES]
    if crowd:
        texts.append("Figurants génériques dans le même style : " + ", ".join(crowd) + ".")
    texts.append("Les objets peuvent avoir un visage cartoon expressif si la scène le demande.")
    return image_prompt_builder.build_scene_prompt(texts, None, character_prefix=prefix, aspect_ratio="9:16",
                                                   style_bible=style_bible, shot_type=direction.get("shot"))


def kb_moves(directions: list, reused_from: list) -> list:
    """Ken Burns move of every beat; a reused picture gets a move different from the beat it was borrowed from."""
    moves = [CAMERA_TO_KB.get(d.get("camera"), "in") for d in directions]
    for i, src in enumerate(reused_from):
        if src is not None:
            moves[i] = next(m for m in _REUSE_MOVES[i % len(_REUSE_MOVES):] + _REUSE_MOVES if m != moves[src])
    return moves


def select_key_beats(directions: list, n: int) -> list:
    """Up to `n` beats worth a moving clip: the opening, then section starts, then shocks, in order of appearance."""
    if n <= 0 or not directions:
        return []
    ranked = [0] + [i for i, d in enumerate(directions) if d.get("section_start")] + \
             [i for i, d in enumerate(directions) if d.get("camera") == "shake"]
    return list(dict.fromkeys(ranked))[:n]


# ---------------------------------------------------------------- captions

def caption_words(lines: list) -> list:
    """[{"text", "start", "end"}] in absolute time for every spoken word (alignment when it matches, else proportional)."""
    words = []
    for line in lines:
        text = str(line["text"])
        times = beats_lib.char_times(text, line.get("alignment"), float(line["dur"]))
        k = 0
        while k < len(text):
            while k < len(text) and text[k].isspace():
                k += 1
            a = k
            while k < len(text) and not text[k].isspace():
                k += 1
            if a < k:
                end = round(line["start"] + times[k - 1][1], 3)
                if words and all(c in beats_lib.CLAUSE_END for c in text[a:k]):
                    words[-1] = {**words[-1], "text": words[-1]["text"] + " " + text[a:k], "end": end}  # "matin !"
                    continue
                words.append({"text": text[a:k], "start": round(line["start"] + times[a][0], 3), "end": end})
    return words


def caption_style_of(script: dict | None) -> str:
    return captions.caption_style_or_default((script or {}).get("caption_style") if isinstance(script, dict) else None)


def write_captions(lines: list, total: float, style: str, out_path: Path) -> Path | None:
    """ASS file in the Standard preset `style`, or None when captions are off."""
    if style == captions.CAPTIONS_OFF:
        return None
    cues = captions.build_cues([(caption_words(lines), total)])
    captions.write_ass(cues, str(out_path), style=style, resolution=RESOLUTION)
    return Path(out_path)


# ---------------------------------------------------------------- IO: images, clips, assembly

def _image_ok(path) -> bool:
    try:
        return path is not None and Path(path).is_file() and Path(path).stat().st_size > 0
    except OSError:
        return False


def generate_images(prompts: list, ports: StoryboardPorts, workdir: Path, max_calls: int) -> tuple[list, list, int]:
    """(image path per beat, index of the beat whose picture was reused or None, paid calls made). Bounded attempts per
    beat and overall; a beat whose picture could not be made reuses the previous one (or the next for the first beats).
    Raises RenderError only when no picture at all could be made."""
    paths, calls = [], 0
    for i, prompt in enumerate(prompts):
        out = workdir / f"beat_{i:03d}.jpg"
        got = None
        for _ in range(max(1, ports.image_attempts)):
            if calls >= max_calls:
                break
            calls += 1
            try:
                result = ports.generate_image(prompt, out)
            except Exception as exc:  # noqa: BLE001 - one failed picture never fails the video
                print(f"       image du plan {i + 1} : échec ({type(exc).__name__})")
                result = None
            if result is not None and _image_ok(out):
                got = out
                break
        paths.append(got)
    if not any(paths):
        raise RenderError("no picture could be generated for this story")
    reused: list = [None] * len(paths)
    for i, p in enumerate(paths):
        if p is None:
            src = next((j for j in range(i - 1, -1, -1) if reused[j] is None and paths[j] is not None), None)
            if src is None:
                src = next(j for j in range(i + 1, len(paths)) if paths[j] is not None)
            reused[i] = src
    return [paths[i] if reused[i] is None else paths[reused[i]] for i in range(len(paths))], reused, calls


def _run(cmd: list, cwd: Path | None = None) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    except FileNotFoundError as exc:
        raise RenderError(f"executable not found: {Path(str(cmd[0])).name}") from exc
    except subprocess.CalledProcessError as exc:
        tail = " | ".join((exc.stderr or "").strip().splitlines()[-4:])
        raise RenderError(f"{Path(str(cmd[0])).name} failed: {tail[:400]}") from exc


def beat_clip(source: Path, frames: int, fps: int, move: str, fade_in: bool, fade_out: bool, out: Path) -> Path:
    """Silent clip of exactly `frames` frames: Ken Burns on a still (Standard helpers of engine/video.py), or a provided
    moving clip cropped to 9:16 and padded with its last frame."""
    seconds = frames / fps
    fades = []
    if fade_in:
        fades.append(f"fade=t=in:st=0:d={FADE_S}")
    if fade_out:
        fades.append(f"fade=t=out:st={max(0.0, seconds - FADE_S):.3f}:d={FADE_S}")
    tail = "".join("," + f for f in fades)
    if str(source).lower().endswith(_VIDEO_EXTS):
        vf = (f"scale={RESOLUTION}:force_original_aspect_ratio=increase:flags=lanczos,crop={WIDTH}:{HEIGHT},fps={fps},"
              f"tpad=stop_mode=clone:stop_duration={seconds:.3f},{video._VIGNETTE},format=yuv420p{tail}")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(Path(source).resolve())]
    else:
        sup = video._scaled_resolution(RESOLUTION, video._KENBURNS_SUPERSAMPLE)
        vf = (f"scale={sup}:force_original_aspect_ratio=increase:flags=lanczos,crop={sup.replace('x', ':')},"
              f"{video._kenburns_filter(move, RESOLUTION, frames, fps)},{video._VIGNETTE},format=yuv420p{tail}")
        # one input frame: the (supersampled) scale runs once and zoompan emits all `frames` frames from it
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(Path(source).resolve())]
    _run(cmd + ["-vf", vf, "-frames:v", str(frames), "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
                "-crf", video._CRF, "-an", str(Path(out).resolve())])
    return Path(out)


def assemble(clips: list, workdir: Path, total: float, fps: int, grain: int, ass: Path | None, out: Path) -> Path:
    """Hard-cut concatenation + film grain + burned captions -> silent clip (the voices are mixed by the pipeline)."""
    listing = workdir / "clips.txt"
    listing.write_text("\n".join(f"file '{Path(c).name}'" for c in clips), encoding="utf-8")
    filters = []
    if grain > 0:
        filters.append(f"noise=alls={int(grain)}:allf=t+u")
    if ass is not None:
        shutil.copyfile(ass, workdir / "captions.ass")
        filters.append("subtitles=captions.ass")
    filters.append("format=yuv420p")
    _run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing.name, "-vf", ",".join(filters),
          "-r", str(fps), "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", FINAL_CRF, "-an",
          "-movflags", "+faststart", str(Path(out).resolve())], cwd=workdir)
    return Path(out)


def _confined_clip(path, workdir: Path) -> Path | None:
    """A key clip is accepted only as an existing video file inside the job directory."""
    if path is None:
        return None
    try:
        p, base = Path(path).resolve(), Path(workdir).resolve()
    except (OSError, TypeError):
        return None
    if base not in p.parents or not p.is_file() or not str(p).lower().endswith(_VIDEO_EXTS):
        return None
    return p


@dataclass
class StoryboardOutcome:
    rendered: RenderResult
    stats: dict = field(default_factory=dict)
    review: list = field(default_factory=list)     # quality.Problem (REVIEW): delivered, but a human looks first


def render(story: dict, script: dict, timeline: dict, lines: list, ports: StoryboardPorts, plan: CostPlan, workdir: Path,
           progress: Callable[[str], None] = lambda label: None) -> StoryboardOutcome:
    """`lines`: the measured lines [{"text", "start", "dur", "alignment", "speaker_id", "shot_index"}]. Runs AFTER the
    credit is reserved: the LLM and image calls here are the paid part."""
    t0 = time.monotonic()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    fps = int(ports.fps)
    total = float(timeline["total"])
    beat_list = beats_lib.merge_to_cap(beats_lib.build_beats(lines), plan.max_images)
    spans = beats_lib.segments(beat_list, lines, total)

    progress("Mise en scène")
    looks = character_looks(story, script)
    title = script.get("title") if isinstance(script, dict) else None
    directed = direction_lib.direct(story, beat_list, looks, call=ports.call_llm, model=ports.llm_model, title=title)
    shots = story.get("shots") or []
    for d, b in zip(directed.beats, beat_list):   # the story's own fades become section changes
        shot = shots[b["shot_index"]] if 0 <= b["shot_index"] < len(shots) else {}
        if b["line_first"] and b["index"] > 0 and shot.get("transition_in") == "fade":
            d["section_start"] = True

    progress("Illustrations")
    style = image_style_bible.resolve_story_style_bible(story.get("style_id"))
    prompts = [beat_prompt(d, style, looks) for d in directed.beats]
    images_dir = workdir / "images"
    images_dir.mkdir(exist_ok=True)
    images, reused_from, image_calls = generate_images(prompts, ports, images_dir, plan.image_calls)
    moves = kb_moves(directed.beats, reused_from)

    sources: list = list(images)
    key_used = 0
    if ports.key_clip and ports.max_key_clips > 0:
        for i in select_key_beats(directed.beats, ports.max_key_clips):
            try:
                clip = ports.key_clip(beat_list[i], directed.beats[i], images[i], spans[i][1] - spans[i][0], workdir)
            except Exception as exc:  # noqa: BLE001 - the still stays when a clip fails
                print(f"       clip clé du plan {i + 1} : échec ({type(exc).__name__})")
                clip = None
            clip = _confined_clip(clip, workdir)
            if clip is not None:
                sources[i], key_used = clip, key_used + 1

    progress("Montage")
    clips_dir = workdir / "clips"
    clips_dir.mkdir(exist_ok=True)
    frame_cuts = [round(a * fps) for a, _ in spans] + [round(total * fps)]
    clips = []
    for i, src in enumerate(sources):
        frames = max(1, frame_cuts[i + 1] - frame_cuts[i])
        fade_in = bool(directed.beats[i].get("section_start"))
        fade_out = i + 1 < len(sources) and bool(directed.beats[i + 1].get("section_start"))
        clips.append(beat_clip(src, frames, fps, moves[i], fade_in, fade_out, clips_dir / f"beat_{i:03d}.mp4"))
    t_render = time.monotonic() - t0

    t1 = time.monotonic()
    style_id = caption_style_of(script)
    ass = write_captions(lines, total, style_id, workdir / "captions_src.ass")
    silent = assemble(clips, clips_dir, total, fps, int(style.get("grain") or 0), ass, workdir / "storyboard_silent.mp4")
    encode_s = time.monotonic() - t1

    reused = sum(1 for r in reused_from if r is not None)
    review = []
    if reused and reused / len(reused_from) > MAX_REUSED_SHARE:
        review.append(quality_lib.Problem(
            "reused_pictures", quality_lib.REVIEW, f"{reused} of {len(reused_from)} pictures were reused after failures",
            f"{reused} illustrations sur {len(reused_from)} ont dû être réutilisées : à vérifier.", {"reused": reused}))
    if directed.source == "fallback":
        review.append(quality_lib.Problem(
            "direction_fallback", quality_lib.REVIEW, "the beat direction fell back to the deterministic plan",
            "La mise en scène automatique n'a pas abouti : les images suivent le texte mot à mot, à vérifier.", {}))
    stats = {
        "renderer": STORYBOARD, "renderer_version": VERSION, "direction_prompt_version": direction_lib.PROMPT_VERSION,
        "direction_source": directed.source, "direction_errors": directed.errors[:3], "llm_calls": directed.llm_calls,
        "llm_cost_usd": direction_lib.llm_cost_usd(directed.usage), "beat_count": len(beat_list),
        "image_count": len(images) - reused, "image_calls": image_calls, "images_reused": reused,
        "key_clips": key_used, "caption_style": style_id, "style_id": style["visual_style_id"],
        "shot_sizes": {s: sum(1 for d in directed.beats if d["shot"] == s) for s in direction_lib.SHOT_SIZES},
    }
    rendered = RenderResult(video_path=silent, render_seconds=round(t_render, 1), encode_seconds=round(encode_s, 1),
                            frames=frame_cuts[-1], width=WIDTH, height=HEIGHT, fps=fps)
    return StoryboardOutcome(rendered=rendered, stats=stats, review=review)
