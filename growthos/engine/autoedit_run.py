"""Orchestration d'un job AutoEdit réclamé par le worker.

Pipeline : source vérifiée -> crédit réservé -> analyse remplaçable -> EDL
validée -> rendu déterministe si l'analyse est réelle -> résultat en review.
Toute erreur devient une erreur structurée
(`{code, message, retryable}`), le crédit réservé est remboursé et les durées
par étape sont conservées dans `run_report` (observabilité).
"""
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
                "playerNumber": job.get("player_number"),
            }
            plan = autoedit.plan_edit(analysis.events, configuration, source, analysis.duration_seconds)
            autoedit.validate_plan(
                plan, source_duration=analysis.duration_seconds, allowed_sources={path},
                known_event_ids={e["id"] for e in analysis.events},
            )

            result_fields = {}
            if not analysis.simulated:
                from engine.autoedit_media import render_plan
                run.advance("rendering", plan=plan)
                rendered = render_plan(local_source, plan, str(Path(work) / "result.mp4"))
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
                "review", plan=plan, quality=autoedit.build_quality(analysis),
                usage=autoedit.build_usage(analysis), expires_at=repo.expiry_from_now(), **result_fields,
            )
        return "review"
    except autoedit.AutoEditError as exc:
        return _fail(client, run, exc, reserved)
    except Exception as exc:
        traceback.print_exc()
        return _fail(client, run, autoedit.AutoEditError(autoedit.ERR_INTERNAL, str(exc) or type(exc).__name__, True), reserved)


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
