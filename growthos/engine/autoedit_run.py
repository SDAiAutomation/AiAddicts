"""Orchestration d'un job AutoEdit réclamé par le worker.

Pipeline : source vérifiée -> crédit réservé -> analyse remplaçable -> EDL
validée -> rendu déterministe si l'analyse est réelle -> résultat en review.
Toute erreur devient une erreur structurée
(`{code, message, retryable}`), le crédit réservé est remboursé et les durées
par étape sont conservées dans `run_report` (observabilité).
"""
import os
import time
import traceback
import tempfile
from pathlib import Path

from engine import autoedit, autoedit_repo as repo, poster


class _Run:
    """Suit les étapes : statut/libellé/progression visibles + durée par étape."""

    def __init__(self, client, job: dict, analyzer: autoedit.VideoAnalyzer):
        self.client = client
        self.job_id = job["id"]
        self.stages: list[dict] = []
        self._current = job["status"]
        self._current_started = time.monotonic()
        self._started = self._current_started
        self.report = {
            "analyzer": analyzer.name,
            "simulated": analyzer.simulated,
            "attempts": job.get("attempts"),
            "creditsReserved": 0,
            "notes": [],
        }

    def _close_current(self) -> None:
        now = time.monotonic()
        self.stages.append({"status": self._current, "durationMs": int((now - self._current_started) * 1000)})
        self._current_started = now

    def snapshot(self) -> dict:
        return {**self.report, "stages": list(self.stages), "totalMs": int((time.monotonic() - self._started) * 1000)}

    def advance(self, status: str, **fields) -> None:
        self._close_current()
        self._current = status
        repo.update_job(
            self.client, self.job_id,
            status=status,
            stage_label=autoedit.STAGE_LABELS[status],
            progress=autoedit.STAGE_PROGRESS.get(status),
            run_report=self.snapshot(),
            **fields,
        )


def process_job(client, job: dict, analyzer: autoedit.VideoAnalyzer) -> str:
    """Traite un job déjà réclamé (status='analyzing'). Retourne le statut
    final ('review', 'completed' ou 'failed'), ne lève jamais."""
    job_id = job["id"]
    run = _Run(client, job, analyzer)
    reserved = False
    try:
        organization_id = job["organization_id"]
        path = autoedit.source_path(organization_id, job_id)

        if not repo.source_exists(client, organization_id, job_id):
            raise autoedit.AutoEditError(
                autoedit.ERR_SOURCE_MISSING, "La vidéo source est introuvable dans le stockage.", False
            )

        cost = autoedit.credit_cost(analyzer)
        if cost > 0:
            if not repo.reserve_credit(client, job_id, cost):
                raise autoedit.AutoEditError(
                    autoedit.ERR_INSUFFICIENT_CREDITS, "Crédits insuffisants pour lancer ce montage.", False
                )
            reserved = True
            run.report["creditsReserved"] = cost
            repo.update_job(client, job_id, credits_reserved=cost)

        with tempfile.TemporaryDirectory(prefix=f"autoedit-{job_id[:8]}-") as work:
            local_source = None
            if not analyzer.simulated:
                local_source = repo.download_source(client, organization_id, job_id, str(Path(work) / "source"))
            source = autoedit.SourceVideo(
                job_id=job_id, storage_path=path, filename=job["input_filename"],
                duration_seconds=_float_or_none(job.get("input_duration_seconds")), local_path=local_source,
            )
            analysis = analyzer.analyze(source)
            if job.get("profile", "sports") == "general" and not analysis.simulated:
                # Les notes de l'analyseur parlent d'actions sportives et de
                # joueur : hors sujet pour une vidéo générale.
                analysis.notes[:] = [
                    "Analyse locale limitée aux signaux visuels et audio : vérifiez que les moments retenus sont les bons."
                ]
            if not analysis.simulated and job["focus"] == "player":
                analysis.notes.append(
                    "Le numéro du joueur n'est pas encore suivi automatiquement : contrôlez chaque plan."
                )
            if not analysis.simulated and job["focus"] == "goals":
                analysis.notes.append(
                    "Les buts ne sont pas encore reconnus sémantiquement : la sélection utilise l'image et l'audio."
                )
            run.report["notes"] = analysis.notes
            repo.update_job(client, job_id, events=analysis.events)

            run.advance("planning")
            configuration = {
                "focus": job["focus"], "style": job["style"], "durationSeconds": job["duration_seconds"],
                "playerNumber": job.get("player_number"), "profile": job.get("profile", "sports"),
            }
            plan = autoedit.plan_edit(analysis.events, configuration, source, analysis.duration_seconds)
            autoedit.validate_plan(
                plan, source_duration=analysis.duration_seconds, allowed_sources={path},
                known_event_ids={e["id"] for e in analysis.events},
            )

            result_fields = {}
            quality = autoedit.build_quality(analysis)
            usage = autoedit.build_usage(analysis)
            if not analysis.simulated:
                from engine.autoedit_media import render_plan
                run.advance("rendering", plan=plan)
                rendered = render_plan(local_source, plan, str(Path(work) / "result.mp4"))
                if job.get("profile", "sports") == "general":
                    rendered = _maybe_add_captions(run, local_source, rendered, plan, work, quality, usage)
                else:
                    rendered = _maybe_add_music(run, local_source, rendered, plan["style"], work, quality, usage)
                # Bucket privé : ce sont des vidéos envoyées par l'utilisateur.
                result_fields["result_video_path"] = repo.upload_result(
                    client, autoedit.result_video_path(organization_id, job_id), rendered, "video/mp4",
                )
                try:
                    poster_path = poster.extract_poster(rendered, str(Path(work) / "poster.jpg"))
                    result_fields["result_poster_path"] = repo.upload_result(
                        client, autoedit.result_poster_path(organization_id, job_id), poster_path, "image/jpeg",
                    )
                except Exception:
                    traceback.print_exc()

            run.advance(
                "review", plan=plan, quality=quality,
                usage=usage, expires_at=repo.expiry_from_now(), **result_fields,
            )
        return "review"
    except autoedit.AutoEditError as exc:
        return _fail(client, run, exc, reserved)
    except Exception as exc:
        traceback.print_exc()
        return _fail(client, run, autoedit.AutoEditError(autoedit.ERR_INTERNAL, str(exc) or type(exc).__name__, True), reserved)


def _maybe_add_music(run: _Run, source: str, rendered: str, style: str, work: str, quality: dict, usage: dict) -> str:
    """Ajoute une musique générée si la source n'a pas de son (voir
    engine/autoedit_music.py). Best-effort : en cas d'échec on garde le
    montage tel quel et on le signale. Retourne le chemin du montage final."""
    from engine import autoedit_media, autoedit_music

    try:
        reason = autoedit_music.silence_reason(source, autoedit_media.probe_has_audio(source))
    except Exception as exc:
        # Détection impossible : on ne touche pas au son du montage.
        run.report["music"] = {"added": False, "reason": "detection_failed", "error": str(exc)[:300]}
        return rendered
    if reason is None:
        run.report["music"] = {"added": False, "reason": "source_has_audio"}
        return rendered
    if not autoedit_music.music_enabled():
        run.report["music"] = {"added": False, "reason": reason, "skipped": "disabled"}
        return rendered
    try:
        seconds = autoedit_media.probe_duration(rendered)
        track = autoedit_music.compose(style, seconds, str(Path(work) / "music.mp3"))
        final = autoedit_music.mux_music(rendered, track, str(Path(work) / "result-music.mp4"), seconds)
    except Exception as exc:
        traceback.print_exc()
        run.report["music"] = {"added": False, "reason": reason, "error": str(exc)[:300]}
        quality["flags"] = [*quality["flags"], "Musique non ajoutée : la génération a échoué, le montage reste muet."]
        quality["manualReview"] = True
        return rendered
    cost = autoedit_music.cost_usd(seconds)
    run.report["music"] = {
        "added": True, "reason": reason, "style": style, "durationSeconds": round(seconds, 2),
        "model": autoedit_music.MUSIC_MODEL, "cost": cost,
    }
    if cost is not None:
        usage["renderCost"] = round((usage.get("renderCost") or 0.0) + cost, 4)
    return final


def _maybe_add_captions(run: _Run, source: str, rendered: str, plan: dict, work: str, quality: dict, usage: dict) -> str:
    """Transcrit la parole d'une video generale et brule les sous-titres. Best-effort."""
    from engine import autoedit_captions, autoedit_media
    try:
        has_audio = autoedit_media.probe_has_audio(source)
    except Exception as exc:
        run.report["captions"] = {"added": False, "reason": "detection_failed", "error": str(exc)[:300]}
        return rendered
    if not has_audio or not os.environ.get("ELEVENLABS_API_KEY"):
        run.report["captions"] = {"added": False, "reason": "no_audio_or_provider"}
        return rendered
    try:
        # Scribe ne reçoit que le montage sélectionné : moins de données envoyées,
        # moins de durée facturée et des timecodes déjà alignés sur le résultat.
        words = autoedit_captions.transcribe(rendered)
        if not words:
            run.report["captions"] = {"added": False, "reason": "no_speech"}
            return rendered
        final = autoedit_captions.burn(rendered, words, str(Path(work) / "result-captioned.mp4"), work)
    except Exception as exc:
        traceback.print_exc()
        run.report["captions"] = {"added": False, "error": str(exc)[:300]}
        quality["flags"] = [*quality["flags"], "Sous-titres non ajoutés : vérifiez le montage avant publication."]
        quality["manualReview"] = True
        return rendered
    seconds = autoedit_media.probe_duration(rendered)
    cost = autoedit_captions.cost_usd(seconds)
    run.report["captions"] = {"added": True, "words": len(words), "model": autoedit_captions.SCRIBE_MODEL, "cost": cost}
    if cost is not None:
        usage["analysisCost"] = round((usage.get("analysisCost") or 0.0) + cost, 4)
    return final


def _fail(client, run: _Run, error: autoedit.AutoEditError, reserved: bool) -> str:
    if reserved:
        try:
            repo.refund_credit(client, run.job_id)
        except Exception:
            # Ne doit pas masquer l'erreur d'origine ; le ledger garde la trace
            # de la réservation non remboursée pour une reprise manuelle.
            traceback.print_exc()
    run._close_current()
    repo.fail_job(client, run.job_id, error.payload(), run.snapshot())
    return "failed"


def _float_or_none(value):
    return None if value is None else float(value)
