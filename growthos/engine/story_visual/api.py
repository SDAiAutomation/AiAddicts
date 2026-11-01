"""Contrats d'API de la future interface Story Studio (pures : validation d'entrée, construction de sortie ; aucune IO).

Opérations prévues, toutes authentifiées et limitées au locataire de l'appelant (le `tenant_id` vient de la session, JAMAIS du corps) :
  plan        POST  {idea, story_type, language, target_duration_s, art_direction?, voice_id?, sources?}  -> {plan, estimate}
  estimate    POST  {plan}                                          -> {estimate, decision}            (ESTIMATION, jamais « coût »)
  edit_scene  PATCH {scene_id, narration?, on_screen_text?, ...}    -> {plan, invalidated: {image, voice}}
  replace     PUT   {scene_id, scene}                               -> {plan, invalidated}
  regenerate  POST  {scene_id}                                      -> {job}   (une image ; plafonnée par scène et par histoire)
  generate    POST  {plan}                                          -> {job}   (idempotent sur le digest du plan)
  status      GET   job                                             -> {state, scenes:[{id,image,voice}], cost:{estimated, spent_by_kind}}
Miroir TypeScript : growthos-web `src/lib/story-studio/visual-api.ts` ; cas partagés : `parity.api_cases()`.
"""
from __future__ import annotations

import copy

from . import cost, pipeline, planner, schema

# champs éditables d'une scène et ce qu'ils invalident (une modification ne régénère que ce qui en dépend)
EDITABLE = {
    "narration": {"voice": True, "image": False},
    "on_screen_text": {"voice": False, "image": False},
    "emotional_tone": {"voice": False, "image": True},
    "visual_intention": {"voice": False, "image": True},
    "image_prompt": {"voice": False, "image": True},
    "visual_direction": {"voice": False, "image": True},
    "characters": {"voice": False, "image": True},
    "duration_s": {"voice": False, "image": False},
    "transition": {"voice": False, "image": False},
    "camera": {"voice": False, "image": False},
    "claim_kind": {"voice": False, "image": False},
    "source_ids": {"voice": False, "image": False},
}
JOB_STATES = ("queued", "planning", "images", "voice", "cards", "render", "done", "failed")
ERROR_CODES = ("invalid_request", "invalid_plan", "unknown_scene", "budget_refused", "quota_exceeded", "regeneration_limit",
               "disabled", "forbidden", "not_found")


def error(code: str, message: str, fields: list | None = None) -> dict:
    assert code in ERROR_CODES
    return {"error": {"code": code, "message": message, "fields": fields or []}}


def parse_plan_request(body) -> tuple[planner.PlanRequest | None, dict | None]:
    """Corps non fiable -> requête typée. Les clés inconnues sont refusées (pas de champ glissé jusqu'au planificateur)."""
    allowed = {"idea", "story_type", "language", "target_duration_s", "art_direction", "voice_id", "sources"}
    if not isinstance(body, dict):
        return None, error("invalid_request", "body must be an object")
    extra = sorted(set(body) - allowed)
    if extra:
        return None, error("invalid_request", "unknown fields", extra)
    request = planner.PlanRequest(idea=body.get("idea"), story_type=body.get("story_type"), language=body.get("language", "fr"),
                                  target_duration_s=body.get("target_duration_s", 60), art_direction=body.get("art_direction"),
                                  sources=body.get("sources", []), voice_id=body.get("voice_id"))
    problems = request.errors()
    return (None, error("invalid_request", "invalid plan request", problems)) if problems else (request, None)


def estimate_payload(plan: dict, env=None, budget: cost.Budget | None = None) -> dict:
    """Estimation affichable. Elle porte toujours `estimated: true` ; un tarif manquant donne `status: unpriced`, pas 0 $."""
    errors = schema.validate_story_plan(plan)
    if errors:
        return error("invalid_plan", "plan is invalid", errors[:12])
    estimate = cost.estimate_episode(plan, env)
    return {"estimate": estimate, "decision": cost.check_budget(estimate, budget or cost.Budget.from_env(env))}


def edit_scene(plan: dict, body) -> tuple[dict | None, dict | None]:
    """Applique une édition partielle sur une COPIE ; renvoie (plan, {"invalidated": {...}}) ou (None, erreur)."""
    if not isinstance(body, dict) or not isinstance(body.get("scene_id"), str):
        return None, error("invalid_request", "scene_id is required")
    fields = {k: v for k, v in body.items() if k != "scene_id"}
    unknown = sorted(set(fields) - set(EDITABLE))
    if unknown or not fields:
        return None, error("invalid_request", "unknown or empty edit", unknown)
    updated = copy.deepcopy(plan)
    scene = next((s for s in updated["scenes"] if s["id"] == body["scene_id"]), None)
    if scene is None:
        return None, error("unknown_scene", "no such scene", [body["scene_id"]])
    invalid = {"image": False, "voice": False}
    for key, value in fields.items():
        if scene.get(key) != value:
            scene[key] = value
            for kind, flag in EDITABLE[key].items():
                invalid[kind] = invalid[kind] or flag
    errors = schema.validate_story_plan(updated)
    if errors:
        return None, error("invalid_plan", "the edit makes the plan invalid", errors[:12])
    return updated, {"invalidated": invalid}


def replace_scene(plan: dict, body) -> tuple[dict | None, dict | None]:
    if not isinstance(body, dict) or not isinstance(body.get("scene"), dict) or not isinstance(body.get("scene_id"), str):
        return None, error("invalid_request", "scene_id and scene are required")
    updated = copy.deepcopy(plan)
    index = next((i for i, s in enumerate(updated["scenes"]) if s["id"] == body["scene_id"]), None)
    if index is None:
        return None, error("unknown_scene", "no such scene", [body["scene_id"]])
    updated["scenes"][index] = {**body["scene"], "id": body["scene_id"]}  # l'identifiant ne change pas
    errors = schema.validate_story_plan(updated)
    if errors:
        return None, error("invalid_plan", "the replacement makes the plan invalid", errors[:12])
    return updated, {"invalidated": {"image": True, "voice": True}}


def parse_regenerate(plan: dict, body) -> tuple[str | None, dict | None]:
    sid = body.get("scene_id") if isinstance(body, dict) else None
    if not isinstance(body, dict) or set(body) - {"scene_id"} or not isinstance(sid, str):
        return None, error("invalid_request", "only scene_id is accepted")
    if sid not in {s["id"] for s in plan["scenes"]}:
        return None, error("unknown_scene", "no such scene", [sid])
    return sid, None


def status_payload(plan: dict, state: str, images: dict | None = None, voices: dict | None = None, cost_report: dict | None = None,
                   error_message: str | None = None) -> dict:
    """État d'un job pour l'interface : progression par scène, coût (estimé / dépensé par nature), erreur réparable."""
    assert state in JOB_STATES
    images, voices = images or {}, voices or {}
    scenes = [{"id": s["id"], "image": images.get(s["id"], {}).get("status", "pending"),
               "voice": voices.get(s["id"], {}).get("status", "pending"),
               "image_generations": images.get(s["id"], {}).get("generations", 0)} for s in plan["scenes"]]
    done = sum(1 for s in scenes if s["image"] == "done") + sum(1 for s in scenes if s["voice"] == "done")
    return {"state": state, "digest": pipeline.plan_digest(plan), "progress": round(done / (2 * len(scenes)), 3), "scenes": scenes,
            "cost": cost_report, "error": error_message, "retryable": state == "failed",
            "disclosure": {"factuality": plan["factuality"], "ai_generated": True}}
