"""Accès base/stockage pour les jobs AutoEdit (`autoedit_jobs`).

Même patron que `engine/repo.py` (file de content_items) : claim atomique par
update conditionné au statut, reprise des orphelins par `updated_at`. Client
service_role uniquement : c'est le worker qui écrit progress/événements/plan/
résultat/erreur ; l'utilisateur ne peut que créer la ligne puis la passer de
'uploading' à 'queued' (voir la migration autoedit_jobs).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine import autoedit

BUCKET = "autoedit-sources"

# Étapes exécutées par un worker : un job qui y reste plus longtemps qu'un run
# normal n'a plus de worker vivant derrière (kill, crash, coupure réseau).
_ACTIVE_STATUSES = ["analyzing", "planning", "rendering"]
_STALE_MINUTES = 15
# Au-delà, on arrête de remettre en file un job qui fait planter les workers.
MAX_ATTEMPTS = 3
# Upload jamais confirmé (onglet fermé...) : la ligne ne doit pas rester
# 'uploading' pour toujours.
_ABANDONED_UPLOAD_HOURS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _failed_fields(error: dict) -> dict:
    return {
        "status": "failed",
        "stage_label": autoedit.STAGE_LABELS["failed"],
        "progress": None,
        "error": error,
    }


def reap_abandoned_uploads(client) -> int:
    cutoff = (_now() - timedelta(hours=_ABANDONED_UPLOAD_HOURS)).isoformat()
    error = autoedit.AutoEditError(
        autoedit.ERR_UPLOAD_INCOMPLETE, "L'envoi de la vidéo n'a jamais été confirmé.", True
    ).payload()
    reaped = (
        client.table("autoedit_jobs")
        .update(_failed_fields(error))
        .eq("status", "uploading")
        .lt("created_at", cutoff)
        .execute()
    )
    return len(reaped.data)


def reclaim_stale_jobs(client) -> int:
    """Remet en 'queued' les jobs orphelins ; ceux déjà réclamés MAX_ATTEMPTS
    fois passent en 'failed' (worker_lost). Retourne le nombre remis en file."""
    cutoff = (_now() - timedelta(minutes=_STALE_MINUTES)).isoformat()
    error = autoedit.AutoEditError(
        autoedit.ERR_WORKER_LOST, "Le traitement a été interrompu à plusieurs reprises.", True
    ).payload()
    (
        client.table("autoedit_jobs")
        .update(_failed_fields(error))
        .in_("status", _ACTIVE_STATUSES)
        .lt("updated_at", cutoff)
        .gte("attempts", MAX_ATTEMPTS)
        .execute()
    )
    requeued = (
        client.table("autoedit_jobs")
        .update({
            "status": "queued",
            "stage_label": autoedit.STAGE_LABELS["queued"],
            "progress": autoedit.STAGE_PROGRESS["queued"],
        })
        .in_("status", _ACTIVE_STATUSES)
        .lt("updated_at", cutoff)
        .lt("attempts", MAX_ATTEMPTS)
        .execute()
    )
    return len(requeued.data)


def claim_job(client) -> dict | None:
    """Réclame le plus ancien job 'queued' : passe à 'analyzing' avec un update
    conditionné au statut encore 'queued' (correct avec plusieurs workers : le
    second, arrivé après, ne récupère aucune ligne). Retourne la ligne réclamée
    ou None si la file est vide."""
    reaped = reap_abandoned_uploads(client)
    if reaped:
        print(f"       {reaped} upload(s) AutoEdit jamais confirmé(s) passé(s) en échec")
    reclaimed = reclaim_stale_jobs(client)
    if reclaimed:
        print(f"       {reclaimed} job(s) AutoEdit orphelin(s) remis en file")

    queued = (
        client.table("autoedit_jobs")
        .select("*")
        .eq("status", "queued")
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not queued.data:
        return None

    job = queued.data[0]
    claimed = (
        client.table("autoedit_jobs")
        .update({
            "status": "analyzing",
            "stage_label": autoedit.STAGE_LABELS["analyzing"],
            "progress": autoedit.STAGE_PROGRESS["analyzing"],
            "attempts": job["attempts"] + 1,
            "error": None,
        })
        .eq("id", job["id"])
        .eq("status", "queued")
        .execute()
    )
    if not claimed.data:
        return None  # un autre worker l'a pris entre-temps
    return claimed.data[0]


def update_job(client, job_id: str, **fields) -> None:
    fields.setdefault("updated_at", _now().isoformat())
    client.table("autoedit_jobs").update(fields).eq("id", job_id).execute()


def fail_job(client, job_id: str, error: dict, run_report: dict | None = None) -> None:
    fields = _failed_fields(error)
    if run_report is not None:
        fields["run_report"] = run_report
    update_job(client, job_id, **fields)


def source_exists(client, organization_id: str, job_id: str) -> bool:
    """La source déposée par le navigateur est-elle bien dans le bucket ?
    (le client peut confirmer 'queued' sans avoir réellement téléversé)."""
    entries = client.storage.from_(BUCKET).list(f"{organization_id}/{job_id}")
    return any(e.get("name") == "source" for e in entries or [])


def download_source(client, organization_id: str, job_id: str, destination: str) -> str:
    """Télécharge la source privée avec le client service_role du worker."""
    payload = client.storage.from_(BUCKET).download(autoedit.source_path(organization_id, job_id))
    if not isinstance(payload, (bytes, bytearray)):
        raise RuntimeError("réponse Storage invalide pendant le téléchargement de la source")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return str(target)


def reserve_credit(client, job_id: str, credits: int) -> bool:
    """Réservation atomique et idempotente (RPC `reserve_autoedit_credit`)."""
    result = client.rpc("reserve_autoedit_credit", {"p_job_id": job_id, "p_credits": credits}).execute()
    return result.data is True


def refund_credit(client, job_id: str) -> bool:
    result = client.rpc("refund_autoedit_credit", {"p_job_id": job_id}).execute()
    return result.data is True
