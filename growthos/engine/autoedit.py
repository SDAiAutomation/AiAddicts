"""AutoEdit — logique pure (statuts, erreurs, EDL, analyseur remplaçable).

Capacité EXPÉRIMENTALE (AUTOEDIT_ENABLED=false par défaut, voir worker.py et
AUTOEDIT_CONTRACT.md). Ce module ne fait AUCUN I/O : l'accès base/stockage vit
dans `engine/autoedit_repo.py`, l'orchestration dans `engine/autoedit_run.py`.

Jalon actuel : `upload -> autoedit_jobs -> claim worker -> statuts -> résultat
SIMULÉ`. L'analyse vidéo réelle n'est pas branchée : `VideoAnalyzer` est
l'interface remplaçable (`analyze(source) -> événements normalisés`), et la
seule implémentation fournie est `SimulatedAnalyzer` (déterministe, gratuite,
n'ouvre jamais la vidéo). Aucun appel Vision payant ne doit être ajouté avant
un benchmark sur quelques vidéos réelles (décision produit 2026-09-23).

Un résultat simulé se déclare toujours comme tel (`quality.flags` +
`manualReview`), jamais présenté comme un vrai montage.
"""
import math
import os
from dataclasses import dataclass, field
from typing import Protocol

# --- Vocabulaire du contrat (AUTOEDIT_CONTRACT.md) -------------------------

STATUSES = ("queued", "uploading", "analyzing", "planning", "rendering", "review", "completed", "failed")
FOCUSES = ("best", "player", "goals")
STYLES = ("hype", "cinematic", "clean", "emotional")
DURATIONS = (15, 30, 60)
EVENT_TYPES = (
    "goal", "shot", "pass", "dribble", "defense", "celebration", "highlight", "audio_peak", "scene_change",
)
EFFECTS = ("slow_motion", "none")

PLAN_VERSION = "autoedit-plan-v1"
SIMULATED_ANALYZER = "simulated"

# Bornes de validation de l'EDL (le modèle propose, le moteur déterministe exécute).
MAX_DECISIONS = 40
MAX_SPEED = 8.0

# Libellés utilisateur, posés par le backend (le frontend affiche `stageLabel`
# tel quel, ne le déduit jamais du statut). En français comme les autres messages
# stockés en base ; les erreurs, elles, sont localisables via `code`.
STAGE_LABELS = {
    "uploading": "Envoi de la vidéo",
    "queued": "En attente de traitement",
    "analyzing": "Analyse de la vidéo",
    "planning": "Choix des meilleurs moments",
    "rendering": "Montage de la vidéo",
    "review": "Prêt pour votre revue",
    "completed": "Montage terminé",
    "failed": "Échec du montage",
}

# Progression connue aux frontières d'étape uniquement (jamais interpolée) :
# `null` reste la valeur correcte quand elle est inconnue.
STAGE_PROGRESS = {"queued": 0, "analyzing": 10, "planning": 60, "rendering": 80, "review": 100, "completed": 100}


class AutoEditError(Exception):
    """Erreur structurée : `code` est localisable côté frontend, `retryable`
    indique si relancer un nouveau job a une chance d'aboutir."""

    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def payload(self) -> dict:
        return {"code": self.code, "message": self.message[:500], "retryable": self.retryable}


# Codes d'erreur émis par le backend (le frontend les localise).
ERR_SOURCE_MISSING = "source_missing"
ERR_INSUFFICIENT_CREDITS = "insufficient_credits"
ERR_PLAN_INVALID = "plan_invalid"
ERR_UPLOAD_INCOMPLETE = "upload_incomplete"
ERR_WORKER_LOST = "worker_lost"
ERR_INTERNAL = "internal_error"


# --- Analyseur remplaçable -------------------------------------------------


@dataclass(frozen=True)
class SourceVideo:
    job_id: str
    storage_path: str  # chemin dans le bucket privé autoedit-sources
    filename: str
    duration_seconds: float | None


@dataclass(frozen=True)
class AnalysisResult:
    events: list[dict]  # AutoEditEvent (forme du contrat)
    duration_seconds: float
    analysis_cost: float | None  # None = non mesuré (jamais deviné)
    simulated: bool
    analyzer: str
    notes: list[str] = field(default_factory=list)


class VideoAnalyzer(Protocol):
    """`analyze(source) -> événements normalisés`. Une implémentation réelle
    (signaux peu coûteux, puis Vision) remplace `SimulatedAnalyzer` sans
    toucher au cycle de job."""

    name: str
    simulated: bool

    def analyze(self, source: SourceVideo) -> AnalysisResult: ...


# Durée supposée quand le client n'a pas fourni la durée de la source. Signalée
# dans les notes du résultat, jamais présentée comme mesurée.
_ASSUMED_DURATION_SECONDS = 120.0
_SIMULATED_EVENT_COUNT = 6


class SimulatedAnalyzer:
    """Événements factices mais déterministes, répartis régulièrement sur la
    durée. Aucun score ni confiance (`null`) : un chiffre inventé pourrait
    passer pour une mesure. Coût d'analyse 0 (aucun appel payant)."""

    name = SIMULATED_ANALYZER
    simulated = True

    def analyze(self, source: SourceVideo) -> AnalysisResult:
        notes = ["Analyse simulée : aucun contenu vidéo n'a été examiné."]
        duration = source.duration_seconds
        if not duration or duration <= 0:
            duration = _ASSUMED_DURATION_SECONDS
            notes.append(f"Durée de la source inconnue : {int(duration)} s supposées.")

        step = duration / _SIMULATED_EVENT_COUNT
        events = []
        for i in range(_SIMULATED_EVENT_COUNT):
            start = round(i * step + step * 0.25, 2)
            end = round(min(start + step * 0.5, duration), 2)
            events.append({
                "id": f"{source.job_id}-sim-{i + 1}",
                "type": "highlight" if i % 2 == 0 else "scene_change",
                "startSeconds": start,
                "endSeconds": end,
                "score": None,
                "confidence": None,
                "subject": None,
                "notes": "Événement simulé (aucune détection réelle).",
            })
        return AnalysisResult(
            events=events, duration_seconds=float(duration), analysis_cost=0.0,
            simulated=True, analyzer=self.name, notes=notes,
        )


def get_analyzer(name: str | None = None) -> VideoAnalyzer:
    """Sélection par `AUTOEDIT_ANALYZER` (défaut : simulated). Un nom inconnu
    échoue au démarrage plutôt que de retomber silencieusement sur autre chose."""
    name = (name or os.environ.get("AUTOEDIT_ANALYZER") or SIMULATED_ANALYZER).strip().lower()
    if name == SIMULATED_ANALYZER:
        return SimulatedAnalyzer()
    raise RuntimeError(
        f"AUTOEDIT_ANALYZER={name!r} inconnu : seul '{SIMULATED_ANALYZER}' est disponible "
        "(aucune analyse réelle branchée)."
    )


# --- Planificateur déterministe (EDL) --------------------------------------

_PADDING_SECONDS = 0.5
_MIN_CLIP_SECONDS = 1.0
_FOCUS_PREFERRED_TYPES = {"goals": ("goal", "celebration"), "player": (), "best": ()}


def plan_edit(events: list[dict], configuration: dict, source: SourceVideo, source_duration: float) -> dict:
    """Construit une EDL déterministe à partir des événements : les mieux
    notés d'abord (à défaut, l'ordre chronologique), jusqu'à remplir la durée
    cible, puis remis dans l'ordre de la source. Volontairement simple : c'est
    la vérification de boucle, pas le montage final. Le résultat passe par
    `validate_plan` avant tout rendu."""
    target = float(configuration["durationSeconds"])
    preferred = _FOCUS_PREFERRED_TYPES.get(configuration.get("focus"), ())

    def rank(event: dict):
        # Tri stable : préférence de type (objectif), score décroissant, chronologie.
        return (
            0 if event["type"] in preferred else 1,
            -(event["score"] if event.get("score") is not None else 0),
            event["startSeconds"],
        )

    chosen, total = [], 0.0
    for event in sorted(events, key=rank):
        if total >= target:
            break
        start = max(0.0, event["startSeconds"] - _PADDING_SECONDS)
        end = min(source_duration, event["endSeconds"] + _PADDING_SECONDS)
        length = min(end - start, target - total)
        if length < _MIN_CLIP_SECONDS:
            continue
        chosen.append({
            "source": source.storage_path,
            "startSeconds": round(start, 2),
            "endSeconds": round(start + length, 2),
            "speed": 1.0,
            "eventId": event["id"],
            "cropTarget": None,
            "effect": None,
            "caption": None,
        })
        total += length

    chosen.sort(key=lambda d: d["startSeconds"])
    return {
        "version": PLAN_VERSION,
        "durationSeconds": round(sum((d["endSeconds"] - d["startSeconds"]) / d["speed"] for d in chosen), 2),
        "style": configuration["style"],
        "decisions": chosen,
    }


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_plan(
    plan: dict,
    *,
    source_duration: float | None,
    allowed_sources: set[str],
    known_event_ids: set[str] | None = None,
    retryable_on_failure: bool = False,
) -> None:
    """Valide l'EDL avant rendu : timecodes dans les limites de la source, durée
    positive, vitesse positive, nombre de clips borné, sources autorisées.
    Lève `AutoEditError(plan_invalid)` ; `retryable` explicite (False pour un
    planificateur déterministe — un bug se reproduira —, True à prévoir pour un
    planificateur à modèle dont la sortie peut varier)."""
    problems = []

    if not isinstance(plan, dict):
        raise AutoEditError(ERR_PLAN_INVALID, "EDL absente ou mal formée.", retryable_on_failure)
    if not plan.get("version"):
        problems.append("version manquante")
    if plan.get("style") not in STYLES:
        problems.append(f"style invalide ({plan.get('style')!r})")
    if not _is_number(plan.get("durationSeconds")) or plan["durationSeconds"] <= 0:
        problems.append("durée du plan non positive")

    decisions = plan.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        problems.append("aucune décision de montage")
        decisions = []
    if len(decisions) > MAX_DECISIONS:
        problems.append(f"trop de clips ({len(decisions)} > {MAX_DECISIONS})")

    for i, d in enumerate(decisions[:MAX_DECISIONS], start=1):
        where = f"clip {i}"
        if not isinstance(d, dict):
            problems.append(f"{where} mal formé")
            continue
        if d.get("source") not in allowed_sources:
            problems.append(f"{where} : source non autorisée")
        start, end, speed = d.get("startSeconds"), d.get("endSeconds"), d.get("speed")
        if not (_is_number(start) and _is_number(end)):
            problems.append(f"{where} : timecodes invalides")
        else:
            if start < 0:
                problems.append(f"{where} : début négatif")
            if end <= start:
                problems.append(f"{where} : durée non positive")
            if source_duration is not None and end > source_duration + 1e-6:
                problems.append(f"{where} : dépasse la source ({end} > {source_duration})")
        if not _is_number(speed) or speed <= 0 or speed > MAX_SPEED:
            problems.append(f"{where} : vitesse invalide ({speed!r})")
        if d.get("effect") is not None and d.get("effect") not in EFFECTS:
            problems.append(f"{where} : effet inconnu ({d.get('effect')!r})")
        if known_event_ids is not None and d.get("eventId") is not None and d["eventId"] not in known_event_ids:
            problems.append(f"{where} : événement inconnu")

    if problems:
        raise AutoEditError(ERR_PLAN_INVALID, "EDL invalide : " + " ; ".join(problems[:8]), retryable_on_failure)


# --- Qualité et coûts (patron quality.py / generation_cost_report) ----------

SIMULATED_FLAG = "Résultat simulé : analyse vidéo non branchée, aucun montage réel produit."


def build_quality(analysis: AnalysisResult) -> dict:
    """`{score, flags, manualReview}`. Un résultat simulé n'a pas de score
    (aucune mesure) et exige toujours une revue."""
    flags = [SIMULATED_FLAG] if analysis.simulated else []
    return {"score": None, "flags": flags, "manualReview": bool(flags)}


def build_usage(analysis: AnalysisResult) -> dict:
    """`{analysisCost, renderCost, currency}`. `None` = non mesuré (jamais
    deviné) ; pas de rendu dans ce jalon donc `renderCost` reste null."""
    return {"analysisCost": analysis.analysis_cost, "renderCost": None, "currency": "USD"}


def credit_cost(analyzer: VideoAnalyzer) -> int:
    """Crédits à réserver pour un job. Quota COMMUN avec Generate, consommation
    propre à AutoEdit (décision produit 2026-09-23). Une analyse simulée ne
    coûte rien : on ne facture pas un résultat factice. Le tarif d'une analyse
    réelle (durée analysée / rendu / variantes) reste à mesurer : le défaut de
    1 crédit est provisoire et surchargeable via AUTOEDIT_CREDIT_COST."""
    if analyzer.simulated:
        return 0
    return max(1, int(os.environ.get("AUTOEDIT_CREDIT_COST", "1")))


def autoedit_enabled() -> bool:
    return os.environ.get("AUTOEDIT_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def source_path(organization_id: str, job_id: str) -> str:
    """Chemin de la source dans le bucket privé — calculé, jamais stocké ;
    doit rester aligné avec la policy `autoedit_sources_upload`."""
    return f"{organization_id}/{job_id}/source"


# --- Vues du contrat (ligne autoedit_jobs -> AutoEditJob / AutoEditResult) --


def to_job_view(row: dict) -> dict:
    """Ligne `autoedit_jobs` (snake_case) -> `AutoEditJob` du contrat."""
    return {
        "jobId": row["id"],
        "status": row["status"],
        "progress": row.get("progress"),
        "stageLabel": row.get("stage_label"),
        "input": {
            "filename": row["input_filename"],
            "durationSeconds": _num(row.get("input_duration_seconds")),
        },
        "configuration": {
            "focus": row["focus"],
            "playerNumber": row.get("player_number"),
            "style": row["style"],
            "durationSeconds": row["duration_seconds"],
        },
        "error": row.get("error"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def to_result_view(row: dict) -> dict | None:
    """Ligne -> `AutoEditResult`, ou None tant que le job n'est ni en
    'review' ni 'completed'."""
    if row["status"] not in ("review", "completed"):
        return None
    plan = row.get("plan") or {}
    return {
        "jobId": row["id"],
        "status": row["status"],
        "videoUrl": row.get("video_url"),
        "posterUrl": row.get("poster_url"),
        "plan": plan,
        "eventsUsed": [d["eventId"] for d in plan.get("decisions", []) if d.get("eventId")],
        "quality": row.get("quality") or {"score": None, "flags": [], "manualReview": False},
        "usage": row.get("usage") or {"analysisCost": None, "renderCost": None, "currency": "USD"},
    }


def _num(value):
    # numeric arrive en str ou Decimal selon le client ; le contrat veut un nombre.
    return None if value is None else float(value)
