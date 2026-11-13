"""Job durable « idée -> storyboard » de Story Studio.

Ce job est volontairement séparé du rendu : un administrateur confirme d'abord le coût maximal de la
planification, relit/édite le storyboard, puis confirme séparément les images, la voix et le montage.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from . import api, cost, formats, planner

PILOT_MAX_USD = 1.0
_KEY = re.compile(r"[A-Za-z0-9:_-]{16,160}")


class PlanningError(RuntimeError):
    pass


@dataclass
class Ports:
    authorize: Callable[[], None] = lambda: None
    moderate: Callable[[dict], None] = lambda script: None
    reserve_credit: Callable[[], bool] = lambda: True
    refund_credit: Callable[[], None] = lambda: None
    release_attempt: Callable[[], None] = lambda: None  # rend la tentative de file quand aucun appel fournisseur n'est parti
    persist: Callable[[dict], None] = lambda script: None
    record_event: Callable[..., None] = lambda name, **props: None
    progress: Callable[[str], None] = lambda label: None
    provider: planner.LLMProvider | None = None
    env: dict | None = None
    ledger: object | None = None
    budget: cost.Budget = field(default_factory=lambda: cost.Budget(max_usd=PILOT_MAX_USD, preferred_usd=PILOT_MAX_USD))


def _planning(script: dict) -> tuple[dict, planner.PlanRequest, float]:
    meta = script.get("story_planning") if isinstance(script, dict) else None
    if not isinstance(meta, dict):
        raise PlanningError("missing story_planning request")
    key = meta.get("idempotency_key")
    cap = meta.get("confirmed_max_usd")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise PlanningError("invalid planning idempotency key")
    if (isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap)
            or cap < 0 or cap > PILOT_MAX_USD):
        raise PlanningError("invalid or excessive confirmed planning ceiling")
    if meta.get("prompt_version") != formats.PLANNER_PROMPT_VERSION:
        raise PlanningError("planning prompt version mismatch; refresh the project")
    request, error = api.parse_plan_request(meta.get("request"))
    if error or request is None:
        fields = ((error or {}).get("error") or {}).get("fields") or []
        raise PlanningError("invalid planning request: " + "; ".join(map(str, fields[:8])))
    return meta, request, float(cap)


def _release(ports: Ports) -> None:
    try:
        ports.release_attempt()
    except Exception as exc:  # noqa: BLE001 - l'erreur initiale reste prioritaire
        print(f"       (tentative de planification non rendue : {type(exc).__name__})")


def run(script: dict, ports: Ports) -> dict:
    """Exécute au plus deux appels bornés. Aucun fournisseur n'est appelé avant tous les garde-fous."""
    ports.authorize()
    if isinstance(script.get("story_plan"), dict):
        return {"script": script, "idempotent_replay": True, "cost_usd": 0.0}
    try:
        meta, request, confirmed_cap = _planning(script)
        pricing, pricing_errors = planner.planner_pricing(ports.env)
        if pricing is None:
            raise PlanningError("planner pricing unavailable: " + "; ".join(pricing_errors))
        if not str((ports.env or {}).get("STORY_PLANNER_MODEL", "")).strip():
            raise PlanningError("planner model is not configured")
        effective_cap = min(PILOT_MAX_USD, ports.budget.max_usd, confirmed_cap)
        if pricing.worst_case_usd > effective_cap + 1e-9:
            raise PlanningError(
                f"planner worst case ${pricing.worst_case_usd:.4f} exceeds confirmed ${effective_cap:.4f} ceiling"
            )
        ports.moderate({"title": request.idea[:120], "blocks": [{"text": request.idea, "visual": request.art_direction or ""}]})
        if ports.ledger is not None and ports.ledger.total() + pricing.worst_case_usd > effective_cap + 1e-9:
            raise PlanningError("confirmed planning ceiling cannot cover the cumulative bounded attempts")
        if not ports.reserve_credit():
            raise PlanningError("credits exhausted")
    except PlanningError:
        # Refus avant tout appel (version, plafond, crédits) : ne consomme pas l'une des tentatives du projet.
        _release(ports)
        raise

    tracker = cost.BudgetTracker(cost.Budget(effective_cap, effective_cap), ledger=ports.ledger)
    try:
        ports.progress("planning")
        provider = ports.provider or planner.openai_chat_provider(ports.env)
        result = planner.plan_story(request, provider, tracker, expected_call_usd=pricing.per_call_usd, env=ports.env)
        if result.plan is None:
            raise PlanningError("story planning failed: " + "; ".join(result.errors[:8]))
        updated = dict(script)
        updated["story_plan"] = result.plan
        updated["simulation"] = False
        updated["script_validated"] = False
        updated["story_planning"] = {
            **meta,
            "state": "completed",
            "attempts": result.attempts,
            "cost_usd": result.cost_usd,
            "cost_kind": result.cost_kind,
        }
        ports.persist(updated)
        ports.record_event("story_planning_completed", attempts=result.attempts, cost_usd=result.cost_usd,
                           cost_kind=result.cost_kind, prompt_version=formats.PLANNER_PROMPT_VERSION)
        return {"script": updated, "cost_usd": result.cost_usd, "attempts": result.attempts}
    except Exception:
        # Un appel parti ou de coût inconnu conserve le crédit. Un refus avant appel ne consomme rien.
        if tracker.total == 0 and not tracker.has_unpriced:
            _release(ports)
            try:
                ports.refund_credit()
            except Exception as exc:  # noqa: BLE001 - l'erreur initiale reste prioritaire
                print(f"       (crédit de planification non remboursé : {type(exc).__name__})")
        raise
