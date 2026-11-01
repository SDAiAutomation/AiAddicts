"""Planificateur narratif : idée -> `story_plan` validé, via un fournisseur LLM INJECTABLE.

`openai_chat_provider()` suit le motif de `engine.story_features.classify` (clé serveur `OPENAI_API_KEY`, endpoint chat,
JSON strict, retry 429 borné) mais n'est jamais appelé par les tests. Le modèle est choisi par `STORY_PLANNER_MODEL` : sans
lui, le fournisseur échoue proprement (on ne devine pas un modèle payant).

Ce qui vient du modèle est NON FIABLE. Le planificateur écrase donc côté serveur tout ce qui ne doit pas être décidé par lui :
identifiant, type, langue, durée, direction artistique, voix et SOURCES (le modèle ne peut citer que les sources fournies dans la
requête : aucune source inventée). Une réponse invalide déclenche au plus une réparation, puis un échec explicite.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

import requests

from . import cost, formats, schema

CHAT_URL = "https://api.openai.com/v1/chat/completions"
MAX_ATTEMPTS = 2
_VOICE_ID = re.compile(r"[A-Za-z0-9]{8,64}")


@dataclass
class LLMResult:
    text: str | None
    usage: dict | None = None   # {"input": n, "output": n} en jetons
    error: str | None = None


LLMProvider = Callable[[str], LLMResult]


def openai_chat_provider() -> LLMProvider:
    """Adaptateur chat OpenAI (PAYANT). Jamais appelé hors d'un pipeline explicitement autorisé."""
    def call(prompt: str) -> LLMResult:
        model = os.environ.get("STORY_PLANNER_MODEL", "").strip()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not model or not api_key:
            return LLMResult(None, None, "planner_not_configured")
        try:
            for attempt in range(4):
                resp = requests.post(CHAT_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=120, json={
                    "model": model, "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}]})
                if resp.status_code != 429 or "insufficient_quota" in resp.text or attempt == 3:
                    break
                time.sleep(5 * (attempt + 1))
            if resp.status_code == 429:
                return LLMResult(None, None, "rate_limited")
            resp.raise_for_status()
            body = resp.json()
            usage = body.get("usage") or {}
            return LLMResult(body["choices"][0]["message"]["content"],
                             {"input": int(usage.get("prompt_tokens") or 0), "output": int(usage.get("completion_tokens") or 0)})
        except (requests.RequestException, KeyError, ValueError, IndexError):
            return LLMResult(None, None, "provider_error")
    return call


@dataclass
class PlanRequest:
    idea: str
    story_type: str
    language: str = "fr"
    target_duration_s: int = 60
    art_direction: str | None = None
    sources: list = field(default_factory=list)
    voice_id: str | None = None

    def errors(self) -> list[str]:
        out = []
        if not isinstance(self.idea, str) or not 3 <= len(self.idea.strip()) <= 1000:
            out.append("idea must be 3–1000 characters")
        if self.story_type not in schema.STORY_TYPES:
            out.append("unknown story_type")
        if self.language not in schema.LANGUAGES:
            out.append("unknown language")
        duration = self.target_duration_s
        if isinstance(duration, float) and duration.is_integer():
            duration = int(duration)  # JSON « 60.0 » : même verdict que le miroir TypeScript (60.0 === 60)
            self.target_duration_s = duration
        if isinstance(duration, bool) or not isinstance(duration, int) or not schema.MIN_DURATION_S <= duration <= schema.MAX_DURATION_S:
            out.append("target_duration_s out of range")
        if self.art_direction is not None and self.art_direction not in schema.ART_DIRECTIONS:
            out.append("unknown art_direction")
        if self.voice_id is not None and not (isinstance(self.voice_id, str) and _VOICE_ID.fullmatch(self.voice_id)):
            out.append("invalid voice_id")
        if not isinstance(self.sources, list) or len(self.sources) > schema.MAX_SOURCES:
            out.append("sources must be a list of at most 12 items")
        else:
            for i, src in enumerate(self.sources):
                if (not isinstance(src, dict) or not schema.is_safe_source_url(src.get("url"))
                        or not isinstance(src.get("id"), str) or not src["id"].strip() or not isinstance(src.get("title"), str) or not src["title"].strip()):
                    out.append(f"sources[{i}] must have id, title and a public https url")
        if self.story_type == "true" and not self.sources:
            out.append("a true story needs at least one supplied source")
        return out


@dataclass
class PlanResult:
    plan: dict | None
    errors: list
    attempts: int
    cost_usd: float | None
    cost_kind: str


def plan_cost_usd(usage: dict | None, env=None) -> float | None:
    env = os.environ if env is None else env
    try:
        p_in, p_out = float(env.get("SCRIPT_PRICE_IN_PER_M", "")), float(env.get("SCRIPT_PRICE_OUT_PER_M", ""))
    except ValueError:
        return None
    if not usage or p_in < 0 or p_out < 0:
        return None
    return (usage.get("input", 0) * p_in + usage.get("output", 0) * p_out) / 1_000_000


def _enforce(plan: dict, request: PlanRequest) -> dict:
    """Le serveur, pas le modèle, décide de ces champs."""
    direction = request.art_direction or formats.strategy_for(request.story_type)["default_art_direction"]
    plan.update(schema_version=schema.SCHEMA_VERSION, story_id=f"st-{uuid.uuid4().hex[:16]}", story_type=request.story_type,
                language=request.language, target_duration_s=request.target_duration_s, art_direction=direction,
                sources=[{"id": s["id"], "title": s["title"], "url": s["url"]} for s in request.sources])
    if request.voice_id:
        plan["voice_id"] = request.voice_id
    else:
        plan.pop("voice_id", None)
    return plan


def plan_story(request: PlanRequest, llm: LLMProvider, tracker: cost.BudgetTracker, *, expected_call_usd: float | None,
               env=None) -> PlanResult:
    """Idée -> plan validé. Réserve le budget AVANT chaque appel ; un coût d'appel inconnu bloque (échec fermé)."""
    problems = request.errors()
    if problems:
        return PlanResult(None, problems, 0, None, cost.UNPRICED)
    direction = request.art_direction or formats.strategy_for(request.story_type)["default_art_direction"]
    prompt = formats.build_planner_prompt(request.story_type, request.idea, request.language, request.target_duration_s,
                                          direction, request.sources)
    errors: list = []
    spent, kind = 0.0, cost.MEASURED
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tracker.reserve(f"plan:{attempt}", expected_call_usd)
        result = llm(prompt)
        usd = plan_cost_usd(result.usage, env) if result.usage else None
        if result.text is not None:
            tracker.record(f"plan:{attempt}", usd)
            spent += usd or 0.0
            kind = cost.UNPRICED if usd is None else kind
        if result.text is None:
            return PlanResult(None, [f"planner provider failed: {result.error or 'unknown'}"], attempt, spent, kind)
        parsed, errors = _parse_enforced(result.text, request)
        if parsed:
            return PlanResult(parsed, [], attempt, spent, kind)
        prompt += "\nTa réponse précédente a été refusée pour ces raisons, corrige-les : " + json.dumps(errors[:12], ensure_ascii=False)
    return PlanResult(None, errors, MAX_ATTEMPTS, spent, kind)


def _parse_enforced(text: str, request: PlanRequest) -> tuple[dict | None, list[str]]:
    try:
        raw = json.loads(text.strip().strip("`").removeprefix("json").strip()) if text.strip().startswith("`") else json.loads(text)
    except ValueError:
        return None, ["model output is not valid JSON"]
    if not isinstance(raw, dict):
        return None, ["model output must be a JSON object"]
    return formats.parse_plan_response(_enforce(raw, request))
