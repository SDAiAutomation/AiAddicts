"""Orchestration of an animated-story job with explicit credit rules (stages are injected; no IO of its own).

Order, and why it matters for money:
  1. everything that can refuse a job runs BEFORE the credit is reserved (contract, layout support, author access,
     moderation, worker readiness, budget) -> nothing to refund;
  2. the credit is reserved, then every later failure (voice, render, mix, quality, publication) refunds it exactly once;
  3. once the video is published the job is a success: bookkeeping errors after that point never refund and never fail it.
The refund itself is the existing atomic, idempotent RPC; a failing refund never hides the error that caused it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import contract, shotplan, timeline as timeline_lib

# rig_v1 draws two characters (one per pack); pack id -> rig role
RIG_ROLES = {"pip_v1": "pip", "rosette_v1": "ros"}
RIG_V1_CATALOG = {
    "settings": sorted(shotplan.BACKGROUNDS), "props": ["alarm_clock"],
    "packs": sorted(RIG_ROLES), "music": ["ragtime_a"],
}
CHARS_PER_SECOND = 14.0   # measured on the prototype French lines (276 characters, about 19 s of speech)
FIXED_SECONDS = 3.1       # lead-in, pauses and payoff tail


class AnimationError(RuntimeError):
    """Base class: the message is safe to show to the author and to log."""


class AnimationUnavailable(AnimationError):
    """This worker cannot render this story (configuration or unsupported layout). Raised before any credit."""


class BudgetExceeded(AnimationError):
    """The estimate is above the story's own budget. Raised before any credit."""


class InsufficientCredits(AnimationError):
    """No credit could be reserved."""


class QualityRejected(AnimationError):
    """The rendered clip failed automatic checks; the credit is refunded."""


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
    check_quality: Callable[[Path], list]                       # problems, empty = pass
    publish: Callable[[Path, dict], dict]                       # (final clip, timeline) -> {"video_url": ..., ...}
    progress: Callable[[str], None] = lambda label: None        # best-effort step label for the library page
    catalog: dict = field(default_factory=dict)
    usd_per_1k_chars: float = 0.3                               # estimate only; never an invoice


def _progress(ports: "Ports", label: str) -> None:
    try:
        ports.progress(label)
    except Exception as exc:  # noqa: BLE001 - a progress label must never fail a paid job
        print(f"       (suivi d'avancement non mis à jour : {type(exc).__name__})")


def rig_roles(story: dict) -> dict:
    """character id -> rig role for the characters whose pack the scene can draw (others are absent)."""
    return {c["id"]: RIG_ROLES[c["pack_id"]] for c in story["characters"] if c["pack_id"] in RIG_ROLES}


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
    layout = rig_v1_layout_errors(story)
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
    for key, value, limit in (("max_tts_chars", tts_chars, budget.get("max_tts_chars")),
                              ("max_render_s", estimate.render_seconds, budget.get("max_render_s")),
                              ("max_usd", usd, budget.get("max_usd"))):
        if limit is not None and value > limit:
            raise BudgetExceeded(f"estimated {key.replace('max_', '')} {value:.1f} is above the budget of {limit}")

    if not ports.reserve_credit():
        raise InsufficientCredits("crédits épuisés pour ce mois-ci")
    ports.record_event("generation_started", renderer="rig_v1", estimated_tts_chars=tts_chars)
    try:
        by_id = {c["id"]: c for c in story["characters"]}
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        lines, wavs = [], []
        _progress(ports, "Voix des personnages")
        for i, shot in enumerate(shots):
            speaker = by_id[shot["speaker_id"]]
            wav = workdir / f"line{i}.wav"
            info = ports.synthesize(shot["dialogue"], speaker["voice_id"], wav)
            lines.append({"who": RIG_ROLES[speaker["pack_id"]], "text": shot["dialogue"], "duration_s": info["duration_s"],
                          "alignment": info["alignment"], "envelope": info["envelope"]})
            wavs.append(wav)
        tl = timeline_lib.build_timeline(lines)
        tl["shots"] = shotplan.build_shot_plan(story, tl, rig_roles(story))
        _progress(ports, "Animation")
        rendered = ports.render(tl, workdir / "render")
        _progress(ports, "Mixage audio")
        final = ports.mix(rendered, [(w, line["start"]) for w, line in zip(wavs, tl["lines"])], tl, workdir / "final.mp4")
        _progress(ports, "Contrôle qualité")
        quality = ports.check_quality(final)
        if quality:
            raise QualityRejected("the rendered clip needs review: " + "; ".join(quality[:4]))
        _progress(ports, "Publication")
        published = ports.publish(final, tl)
    except Exception:
        try:
            ports.refund_credit()
        except Exception as refund_error:  # noqa: BLE001 - the original failure must not be hidden
            print(f"       (remboursement du crédit non appliqué : {type(refund_error).__name__})")
        raise
    try:
        ports.record_event("generation_completed", renderer="rig_v1", duration_s=tl["total"])
    except Exception as exc:  # noqa: BLE001 - the video is delivered; never turn it into a failure
        print(f"       (événement de fin non enregistré : {type(exc).__name__})")
    return {"video_url": published.get("video_url"), "timeline_total_s": tl["total"], **{k: v for k, v in published.items() if k != "video_url"}}
