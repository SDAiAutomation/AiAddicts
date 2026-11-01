"""Pipeline récit illustré de bout en bout, à PORTS injectés (même principe que `story_animation.pipeline`).

Étapes :
    validation -> budget (échec fermé) -> modération -> autorisation -> quota -> crédit -> images -> voix
    -> calage -> cartes -> sous-titres Faceloop -> rendu -> contrôle qualité -> publication.

Remboursement du crédit (règle A, sans exception) :
    - remboursé SEULEMENT si rien n'a été dépensé (total nul ET aucun coût inconnu) ;
    - jamais après une publication réussie ;
    - un échec de remboursement ne masque jamais l'erreur d'origine.

Idempotence :
    un job déjà terminé (même locataire, même plan) renvoie son résultat sans rappeler aucun fournisseur.

Fournisseurs :
    ce sont des ports. Doublures hors ligne par défaut dans les tests ; adaptateurs réels
    (`orchestrator.openai_provider`, `voice.elevenlabs_provider`) fournis par le worker uniquement
    derrière `STORY_VISUAL_ENABLED`.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .cost import BudgetExceeded
from . import cache as cache_mod
from .. import captions
from . import cost, orchestrator, overlay, render, schema, store, subtitles, timing, voice

_SAFE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class PipelineError(RuntimeError):
    pass


@dataclass
class Ports:
    image_provider: orchestrator.Provider
    voice_provider: voice.VoiceProvider
    reserve_credit: Callable[[], bool] = lambda: True
    refund_credit: Callable[[], None] = lambda: None
    authorize: Callable[[], None] = lambda: None
    moderate: Callable[[dict], None] = lambda script: None
    consume_quota: Callable[[], bool] = lambda: True
    record_event: Callable[..., None] = lambda name, **props: None
    progress: Callable[[str], None] = lambda label: None
    publish: Callable[[Path, dict, dict], dict] | None = None
    env: dict | None = None
    budget: cost.Budget = field(default_factory=cost.Budget)
    image_cache: cache_mod.DiskImageCache | None = None
    voice_cache: cache_mod.DiskImageCache | None = None
    ledger: object | None = None          # `ledger.DurableLedger`: cumulative spend of the episode (None only in offline unit tests)
    render_fps: int = render.FPS          # 30 en production ; les tests hors ligne rapides abaissent fps/preset
    render_preset: str = "veryfast"


def plan_digest(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:24]


def moderation_view(plan: dict) -> dict:
    """Le plan vu comme un script Standard, pour réutiliser `moderation.check_script` sans le modifier."""
    return {"title": plan.get("title", ""), "blocks": [{"text": s["narration"], "visual": s["image_prompt"]} for s in plan["scenes"]]}


def quality_issues(info: dict, timeline: dict) -> list[str]:
    """Contrôles d'après-rendu : conteneur, codecs, résolution, durée alignée sur la timeline."""
    issues = []
    video, audio = info.get("video", {}), info.get("audio", {})
    if (video.get("width"), video.get("height")) != (render.W, render.H):
        issues.append(f"resolution {video.get('width')}x{video.get('height')} is not {render.W}x{render.H}")
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        issues.append("video must be h264 yuv420p")
    if audio.get("codec_name") != "aac":
        issues.append("audio must be aac")
    if abs(info.get("duration", 0) - timeline["total_s"]) > 0.5:
        issues.append(f"duration {info.get('duration', 0):.2f}s differs from timeline {timeline['total_s']:.2f}s")
    return issues


def run(script: dict, ports: Ports, work_dir: str | Path, *, tenant_id: str) -> dict:
    caption_style = captions.caption_style_or_default(script.get("caption_style") if isinstance(script, dict) else None)
    # Order of the guards (the feature flag comes first, in the worker routing): administrator, plan, rates and budget, moderation,
    # then lock, quota, credit and providers. A refused caller learns nothing about rates or plans and costs nothing.
    ports.authorize()
    if not _SAFE.fullmatch(tenant_id or ""):
        raise PipelineError("invalid tenant id")
    plan = script.get("story_plan") if isinstance(script, dict) else None
    errors = schema.validate_story_plan(plan)
    if errors:
        raise PipelineError("invalid story plan: " + "; ".join(errors[:5]))
    env = ports.env
    estimate = cost.estimate_episode(plan, env)
    decision = cost.check_budget(estimate, ports.budget)
    if not decision["allowed"]:
        raise PipelineError("budget refused: " + decision["message"])
    if not plan.get("voice_id") and not _default_voice(env):
        raise PipelineError("no voice configured (plan.voice_id or STORY_DEFAULT_VOICE_ID)")
    ports.moderate(moderation_view(plan))

    digest = plan_digest(plan)
    folder = Path(work_dir).resolve() / tenant_id / plan["story_id"]
    folder.mkdir(parents=True, exist_ok=True)
    done_path = folder / "done.json"
    with store.job_lock(folder):  # le verrou précède quota et crédit : une exécution refusée ne consomme rien
        try:
            done = json.loads(done_path.read_text(encoding="utf-8"))
            if done.get("digest") == digest and done.get("caption_style") == caption_style and Path(done["video"]).is_file():
                return {**done, "idempotent_replay": True}
        except (OSError, ValueError, KeyError):
            pass
        if not ports.consume_quota():
            raise PipelineError("job quota exceeded for this tenant")
        if ports.ledger is not None:  # before the credit: an episode that cannot spend must not even take one
            try:
                remaining = ports.ledger.remaining()
            except BudgetExceeded as exc:
                raise PipelineError("spend ledger unavailable: " + str(exc)) from exc
            if remaining <= 0:
                raise PipelineError("episode spend ceiling already reached by earlier runs")
        if not ports.reserve_credit():
            raise PipelineError("credits exhausted")
        return _execute(plan, ports, folder, done_path, digest, tenant_id, work_dir, env, estimate, decision,
                        cost.BudgetTracker(ports.budget, ledger=ports.ledger), caption_style)


def review_fields(result: dict) -> dict:
    """Champs de la ligne de contenu pour un clip livré : des sous-titres douteux ne passent jamais pour « prêts » (état `quality_check` existant,
    sans migration : un humain regarde avant publication) ; sinon `video` et drapeaux d'un run précédent effacés."""
    flags = [f"Contrôle qualité : {issue}" for issue in (result.get("review") or [])][:8]
    return {"status": "quality_check", "quality_flags": flags} if flags else {"status": "video", "quality_flags": []}


def _execute(plan, ports, folder, done_path, digest, tenant_id, work_dir, env, estimate, decision, tracker, caption_style) -> dict:
    published = False
    try:
        ports.record_event("generation_started", renderer="story_visual", estimated_usd=decision["total_usd"], estimated=True)
        ports.progress("images")
        unit, _ = cost.image_unit_cost(env)
        images = orchestrator.generate_scene_images(
            plan, tenant_id=tenant_id, work_dir=work_dir, provider=ports.image_provider, tracker=tracker,
            expected_unit_usd=unit, disk_cache=ports.image_cache)
        failed = [sid for sid, m in images.items() if m["status"] != "done"]
        if failed:
            raise PipelineError("image generation failed for: " + ", ".join(failed))
        ports.progress("voice")
        voices = voice.synthesize_story(plan, tenant_id=tenant_id, work_dir=work_dir, provider=ports.voice_provider,
                                        tracker=tracker, voice_id=None if plan.get("voice_id") else _default_voice(env),
                                        rate_per_1k=voice.voice_rate_per_1k(env), disk_cache=ports.voice_cache)
        failed = [sid for sid, m in voices.items() if m["status"] != "done"]
        if failed:
            raise PipelineError("voice synthesis failed for: " + ", ".join(failed))
        timeline = timing.schedule(plan, voice.measured_durations(voices))
        overlaps = timing.check_no_overlap(timeline)
        if overlaps:
            raise PipelineError("; ".join(overlaps))
        ports.progress("cards")
        cards = []
        for scene in plan["scenes"]:
            card = folder / f"card-{scene['id']}.jpg"
            overlay.compose_card(images[scene["id"]]["path"], card)
            cards.append(card)
        cues = subtitles.build_cues(timeline, voices)
        ass = subtitles.write(cues, folder, plan["story_id"], caption_style)
        ports.progress("render")
        video = folder / f"{plan['story_id']}.mp4"
        info = render.render_story(cards, timeline, [voices[s["id"]]["path"] for s in plan["scenes"]], video, folder / "clips", fps=ports.render_fps, preset=ports.render_preset,
                                 captions_ass=ass)
        issues = quality_issues(info, timeline) + subtitles.issues(cues, ass, caption_style, timeline["total_s"])
        if any(i.startswith(("resolution", "video", "audio", "duration")) for i in issues):
            raise PipelineError("quality check failed: " + "; ".join(issues))
        report = _report(plan, estimate, decision, tracker, images, voices)
        result = {"digest": digest, "caption_style": caption_style, "video": str(video), "timeline": timeline, "cost": report, "review": issues, "needs_review": bool(issues),
                  "factuality": plan["factuality"], "sources": plan.get("sources", [])}
        if ports.publish:
            result["published"] = ports.publish(video, timeline, result)
            published = True
        done_path.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        ports.record_event("generation_completed", renderer="story_visual", duration_s=timeline["total_s"],
                           measured_usd=report["spent_usd"], cost_complete=report["complete"])
        return result
    except BaseException:
        # Règle A : rembourser SEULEMENT si rien n'a été dépensé (total nul ET aucun coût inconnu), et jamais après une publication réussie.
        if published:
            print("       (crédit non remboursé : la vidéo est déjà publiée)")
        elif tracker.total > 0 or tracker.has_unpriced:
            print(f"       (crédit non remboursé : dépense engagée ${tracker.total:.4f}, coût inconnu={tracker.has_unpriced})")
        else:
            try:
                ports.refund_credit()
            except Exception as exc:  # noqa: BLE001 - never mask the original failure
                print(f"       (remboursement du crédit non confirmé : {type(exc).__name__})")
        raise


def _default_voice(env) -> str | None:
    import os
    return ((env if env is not None else os.environ).get("STORY_DEFAULT_VOICE_ID") or "").strip() or None


def _report(plan, estimate, decision, tracker, images, voices) -> dict:
    """Estimation et dépense ne sont jamais mélangées : `estimated_usd` (avant) / `spent_usd` par nature (après)."""
    by_kind = tracker.total_by_kind()
    return {"estimated_usd": estimate["total_usd"], "estimated": True, "budget_status": decision["status"],
            "spent_usd": tracker.total, "spent_by_kind": by_kind,
            "complete": not tracker.has_unpriced,  # False : au moins un appel dont le coût est inconnu -> total sous-évalué
            "lines": dict(tracker.spent), "image_cache_hits": sum(1 for m in images.values() if m.get("cache_hit")),
            "voice_cache_hits": sum(1 for m in voices.values() if m.get("cache_hit"))}
