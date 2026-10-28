"""Orchestration of an animated-story job with explicit credit rules (stages are injected; no IO of its own).

Order, and why it matters for money:
  1. everything that can refuse a job runs BEFORE the credit is reserved (contract, layout support, author access,
     moderation, worker readiness, budget) -> nothing to refund;
  2. the credit is reserved, then every later failure (voice, render, mix, quality, publication) refunds it exactly once;
  3. once the video is published the job is a success: bookkeeping errors after that point never refund and never fail it.
The refund itself is the existing atomic, idempotent RPC; a failing refund never hides the error that caused it.

Two renderers share these rules (`Ports.renderer`): "rig_v1" (Godot puppets, `ports.render`) and "storyboard" (one
illustrated beat every 2-4 s, see storyboard.py). For the storyboard, the upper cost of the pictures, their retries and the
direction call is added to the estimate and checked against the story budget and a server cap BEFORE the reservation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import contract, quality as quality_lib, shotplan, timeline as timeline_lib

# looks the scene can print the same drawings in (scene.gd LOOKS); the first one is the reference look and the default
STYLES = ("noir_1930", "sepia_1930", "cyanotype_1930", "couleur_1930")
# rig_v1 draws two characters (one per pack); pack id -> rig role
RIG_ROLES = {"pip_v1": "pip", "rosette_v1": "ros"}
NARRATOR_ROLE = "narrator"
RIG_V1_CATALOG = {
    "settings": sorted(shotplan.BACKGROUNDS), "props": ["alarm_clock"],
    "packs": sorted(RIG_ROLES), "music": ["ragtime_a"], "styles": list(STYLES),
}
CHARS_PER_SECOND = contract.SPEECH_CHARS_PER_SECOND_SLOW   # conservative estimate (the contract also keeps the measured fast rate)
FIXED_SECONDS = contract.FIXED_SECONDS                     # lead-in, pauses and payoff tail


class AnimationError(RuntimeError):
    """Base class: the message is safe to show to the author and to log."""


class AnimationUnavailable(AnimationError):
    """This worker cannot render this story (configuration or unsupported layout). Raised before any credit."""


class BudgetExceeded(AnimationError):
    """The estimate is above the story's own budget. Raised before any credit."""


class InsufficientCredits(AnimationError):
    """No credit could be reserved."""


class QualityRejected(AnimationError):
    """The rendered clip is unusable (blocking problems); the credit is refunded. Review-level problems do NOT raise:
    the clip is delivered in the existing `quality_check` state."""


@dataclass
class Ports:
    authorize: Callable[[], None]                               # admin-only beta; raises when denied
    moderate: Callable[[dict], None]                            # whole script; raises ModerationError
    ready: Callable[[], list]                                   # reasons this worker cannot render (empty = ready)
    estimate: Callable[[float, int], object]                    # (video seconds, tts chars) -> CostEstimate
    reserve_credit: Callable[[], bool]
    refund_credit: Callable[[], None]
    record_event: Callable[..., None]
    synthesize: Callable[[str, str, Path], dict]                # (text, voice_id, wav path) -> {duration_s, alignment, envelope}
    render: Callable[[dict, Path], object]                      # (timeline, workdir) -> RenderResult
    mix: Callable[[object, list, dict, Path], Path]             # (render result, [(wav, start)], timeline, out path) -> final clip
    check_quality: Callable[[Path], list]                       # [quality.Problem]; empty = pass
    publish: Callable[[Path, dict, list], dict]                 # (final clip, timeline, review problems) -> {"video_url": ..., ...}
    progress: Callable[[str], None] = lambda label: None        # best-effort step label for the library page
    catalog: dict = field(default_factory=dict)
    usd_per_1k_chars: float = 0.3                               # estimate only; never an invoice
    renderer: str = "rig_v1"                                    # "rig_v1" (Godot puppets) | "storyboard" (illustrated beats)
    storyboard: object = None                                   # storyboard.StoryboardPorts when renderer == "storyboard"


def _progress(ports: "Ports", label: str) -> None:
    try:
        ports.progress(label)
    except Exception as exc:  # noqa: BLE001 - a progress label must never fail a paid job
        print(f"       (suivi d'avancement non mis à jour : {type(exc).__name__})")


def rig_roles(story: dict) -> dict:
    """character id -> rig role for the characters whose pack the scene can draw (others are absent)."""
    roles = {c["id"]: RIG_ROLES[c["pack_id"]] for c in story["characters"] if c["pack_id"] in RIG_ROLES}
    narrator = story.get("narrator")
    if isinstance(narrator, dict) and narrator.get("id"):
        roles[narrator["id"]] = NARRATOR_ROLE   # a voice without a body: the scene draws the setting and the listeners
    return roles


def rig_v1_layout_errors(story: dict) -> list:
    """What the packaged scene can draw: characters from the two known packs, at most one per rig role, and one shot per
    spoken line (the scene's shots are the story's shots)."""
    errors = []
    seen = {}
    for c in story["characters"]:
        role = RIG_ROLES.get(c["pack_id"])
        if role is None:
            errors.append(f"pack {c['pack_id']!r} is not supported by rig_v1")
        elif role in seen:
            errors.append(f"characters {seen[role]!r} and {c['id']!r} both use the {role!r} rig; rig_v1 draws one character per pack")
        else:
            seen[role] = c["id"]
    return errors


def estimated_video_seconds(tts_chars: int) -> float:
    return tts_chars / CHARS_PER_SECOND + FIXED_SECONDS


def run(script: dict, ports: Ports, workdir: Path) -> dict:
    story = script.get("story") if isinstance(script, dict) else None
    errors = contract.validate_animation_story(story, ports.catalog)
    if errors:
        raise ValueError("Animated story not renderable: " + "; ".join(errors[:5]))
    storyboard = ports.renderer == "storyboard"
    if storyboard:
        from . import storyboard as storyboard_lib   # local: the rig path never loads the image stack
        if ports.storyboard is None:
            raise AnimationUnavailable("the storyboard renderer is not configured on this worker")
    else:
        layout = rig_v1_layout_errors(story)   # the puppets draw one character per pack; the storyboard has no such limit
        if layout:
            raise AnimationUnavailable("; ".join(layout))

    ports.authorize()
    ports.moderate(script)
    problems = ports.ready()
    if problems:
        raise AnimationUnavailable("animated rendering is not available on this worker: " + "; ".join(problems))

    shots = story["shots"]
    tts_chars = sum(len(s["dialogue"]) for s in shots)
    seconds = estimated_video_seconds(tts_chars)
    estimate = ports.estimate(seconds, tts_chars)
    budget = story.get("budget") or {}
    usd = tts_chars / 1000.0 * ports.usd_per_1k_chars
    cost_plan = None
    if storyboard:
        # images (+ retries) and the direction call are paid AFTER the reservation: their upper bound is checked now
        cost_plan = storyboard_lib.plan_costs(seconds, ports.storyboard)
        usd += cost_plan.extra_usd
        if usd > ports.storyboard.max_usd:
            raise BudgetExceeded(f"estimated usd {usd:.2f} is above the server cap of {ports.storyboard.max_usd}")
    for key, value, limit in (("max_tts_chars", tts_chars, budget.get("max_tts_chars")),
                              ("max_render_s", estimate.render_seconds, budget.get("max_render_s")),
                              ("max_usd", usd, budget.get("max_usd"))):
        if limit is not None and value > limit:
            raise BudgetExceeded(f"estimated {key.replace('max_', '')} {value:.1f} is above the budget of {limit}")

    if not ports.reserve_credit():
        raise InsufficientCredits("crédits épuisés pour ce mois-ci")
    started = {"renderer": ports.renderer, "estimated_tts_chars": tts_chars}
    if cost_plan is not None:
        started.update(estimated_cost_usd=round(usd, 3), max_images=cost_plan.max_images,
                       max_image_calls=cost_plan.image_calls)
    ports.record_event("generation_started", **started)
    stats: dict = {}
    try:
        by_id = {c["id"]: {"voice_id": c["voice_id"], "role": RIG_ROLES.get(c["pack_id"], c["id"])} for c in story["characters"]}
        if isinstance(story.get("narrator"), dict):
            by_id[story["narrator"]["id"]] = {"voice_id": story["narrator"]["voice_id"], "role": NARRATOR_ROLE}
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        lines, wavs = [], []
        _progress(ports, "Voix des personnages")
        for i, shot in enumerate(shots):
            speaker = by_id[shot["speaker_id"]]
            wav = workdir / f"line{i}.wav"
            info = ports.synthesize(shot["dialogue"], speaker["voice_id"], wav)
            lines.append({"who": speaker["role"], "text": shot["dialogue"], "duration_s": info["duration_s"],
                          "alignment": info["alignment"], "envelope": info["envelope"]})
            wavs.append(wav)
        schema = story.get("animation_schema_version", contract.ANIMATION_SCHEMA_VERSION)
        tl = timeline_lib.build_timeline(lines, max_total=contract.LIMITS[schema]["max_duration"])
        tl["style"] = story.get("style_id") or STYLES[0]
        extra_review = []
        if storyboard:
            measured = [{"text": tl_line["text"], "start": tl_line["start"], "dur": tl_line["dur"],
                         "alignment": line["alignment"], "speaker_id": shot["speaker_id"], "shot_index": i}
                        for i, (tl_line, line, shot) in enumerate(zip(tl["lines"], lines, shots))]
            outcome = storyboard_lib.render(story, script, tl, measured, ports.storyboard, cost_plan, workdir / "storyboard",
                                            progress=lambda label: _progress(ports, label))
            rendered, stats, extra_review = outcome.rendered, outcome.stats, outcome.review
        else:
            tl["shots"] = shotplan.build_shot_plan(story, tl, rig_roles(story))
            _progress(ports, "Animation")
            rendered = ports.render(tl, workdir / "render")
        _progress(ports, "Mixage audio")
        final = ports.mix(rendered, [(w, line["start"]) for w, line in zip(wavs, tl["lines"])], tl, workdir / "final.mp4")
        _progress(ports, "Contrôle qualité")
        problems = list(ports.check_quality(final)) + list(extra_review)
        blocking = [p for p in problems if p.severity == quality_lib.BLOCKING]
        if blocking:
            raise QualityRejected("the rendered clip is unusable: " + "; ".join(p.text for p in blocking[:4]))
        review = [p for p in problems if p.severity == quality_lib.REVIEW]
        _progress(ports, "Publication")
        published = ports.publish(final, tl, review)
    except Exception:
        try:
            ports.refund_credit()
        except Exception as refund_error:  # noqa: BLE001 - the original failure must not be hidden
            print(f"       (remboursement du crédit non appliqué : {type(refund_error).__name__})")
        raise
    try:
        done = {"renderer": ports.renderer, "duration_s": tl["total"], "status": "quality_check" if review else "video"}
        if storyboard:
            done.update(estimated_cost_usd=round(usd, 3), **{k: stats.get(k) for k in (
                "beat_count", "image_count", "image_calls", "images_reused", "direction_source", "llm_calls",
                "llm_cost_usd", "key_clips", "caption_style", "renderer_version", "direction_prompt_version")})
        ports.record_event("generation_completed", **done)
    except Exception as exc:  # noqa: BLE001 - the video is delivered; never turn it into a failure
        print(f"       (événement de fin non enregistré : {type(exc).__name__})")
    return {"video_url": published.get("video_url"), "timeline_total_s": tl["total"], "needs_review": bool(review),
            **{k: v for k, v in published.items() if k != "video_url"}}
