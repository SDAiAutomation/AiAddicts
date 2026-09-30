"""Phase 4 — semantic stock-footage planning + deterministic retrieval/ranking.

WHY (benchmark `c-explainer.stock_footage`): ~2/6 stock scenes were semantic
misses. Root causes, all in the old `visuals._fetch_stock_clip` path:
  1. the query was a bag of the first 2 keywords of the `visual` text, filtered
     with a FRENCH stop-word list, sent to an English-indexed library;
  2. the niche's first word was appended ("productivite") and polluted it;
  3. ONE query, no broadening, and the first acceptable clip won — no ranking;
  4. no diversity: nothing stopped the same clip / same videographer / same
     "person on phone" idea from recurring across blocks.

This module separates WHAT THE NARRATION SAYS from WHAT THE VIEWER SHOULD SEE:

- `plan_blocks`   : one `stockPlan` per block (visualConcept/subject/action/
                    environment/searchQueries/avoidQueries). Precedence: a plan
                    already on the block (`block["stockPlan"]`, future web
                    integration) > ONE LLM call for the whole video (cached) >
                    deterministic legacy derivation. Never one call per block.
- `build_ladder`  : deterministic ordered query ladder (specific -> broad).
- `rank_candidates`: deterministic scoring from REAL Pexels metadata only
                    (dimensions, duration, URL slug words, result rank) plus
                    the block's shot plan and the in-video diversity state.
                    No vision model, no embeddings.
- `select_stock_clips`: walks the ladder per block, stops at the first level
                    that yields an acceptable clip, records everything.

Pure logic: network access is injected (`search_fn`, `download_fn`) so every
rule is unit-testable without consuming Pexels quota.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests

CHAT_URL = "https://api.openai.com/v1/chat/completions"

PLAN_VERSION = 1
MAX_QUERIES_PER_PLAN = 4
MAX_SEARCHES_PER_BLOCK = 5  # hard cap on Pexels calls (ladder + orientation widening)
CANDIDATES_PER_SEARCH = 15
MIN_PORTRAIT_POOL = 3  # below this many portrait hits, also search any orientation

ACCEPT_RELEVANCE = 0.25  # min slug/query token overlap to accept a semantic plan's clip
ACCEPT_SCORE = 3.0
LOW_CONFIDENCE_MAX_RANK = 2  # best-available fallback only trusts Pexels' own top results

_DUPLICATE_PENALTY = 10.0
_CONSECUTIVE_PENALTY = 20.0
_SAME_CREATOR_PENALTY = 1.0
_PREV_REPEAT_WEIGHT = 2.0
_ANY_REPEAT_WEIGHT = 1.0
_AVOID_PENALTY = 3.0
_AVOID_PENALTY_CAP = 6.0
# Slug words that mean "not live-action footage" (3D/animated/template clips
# break a photographic B-roll sequence). Penalised unless the query asked for them.
_NON_FOOTAGE_TOKENS = {"animation", "animated", "3d", "render", "rendering", "cartoon", "illustration",
                       "template", "intro", "motion", "graphic", "graphics", "cgi"}
_NON_FOOTAGE_PENALTY = 2.5
_LEVEL_BONUS = (1.0, 0.6, 0.3, 0.0)
_SHOT_HINT_BONUS = 0.4
_DEFAULT_BLOCK_SECONDS = 6.0

_STOP = {
    "a", "an", "the", "of", "in", "on", "at", "with", "and", "or", "to", "for", "by", "from",
    "video", "footage", "shot", "view", "stock", "free", "hd", "4k", "pexels",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Slug words that genuinely indicate the framing a block asked for. Small,
# deliberately conservative: only used as a +0.4 tie-breaker.
_SHOT_SLUG_HINTS = {
    "close_up": {"close", "closeup", "macro", "detail", "details"},
    "insert": {"close", "closeup", "macro", "detail", "details", "hands", "hand", "screen"},
    "wide": {"wide", "aerial", "panorama", "skyline", "exterior", "drone", "cityscape"},
    "pov": {"pov", "hands", "hand", "first"},
}

# shotType/visualPurpose -> what the planning prompt should look for.
SHOT_GUIDANCE = {
    "wide": "environment / context, the place where it happens",
    "medium": "a person visibly doing something (action)",
    "close_up": "a face or a hand: emotional response or a precise gesture",
    "insert": "one object/detail that supports the narration",
    "pov": "what the person sees or holds, hands in frame",
}
PURPOSE_GUIDANCE = {
    "hook": "a striking, instantly readable image",
    "establish": "set the place/context",
    "action": "visible human action",
    "evidence": "an object or detail that proves the point",
    "reaction": "an emotional human response",
    "explain": "a clear, literal illustration",
    "reveal": "the consequence or surprise becoming visible",
    "payoff": "a visually satisfying result",
    "cta": "an open, inviting, human closing image",
}


# --- Plan schema ----------------------------------------------------------

def _clean_phrase(value: object, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len].strip()


def _clean_queries(raw: object, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[frozenset] = set()
    out: list[str] = []
    for item in raw:
        q = _clean_phrase(item, 60)
        words = _TOKEN_RE.findall(q.lower())
        if not (1 <= len(words) <= 8):
            continue
        key = frozenset(words)
        if key in seen:
            continue
        seen.add(key)
        out.append(" ".join(words))
        if len(out) >= limit:
            break
    return out


def normalize_plan(raw: object) -> dict | None:
    """Validated, size-bounded `stockPlan`, or None if unusable. Tolerates
    missing optional fields; needs at least one search query OR a subject."""
    if not isinstance(raw, dict):
        return None
    plan = {
        "visualConcept": _clean_phrase(raw.get("visualConcept"), 120),
        "subject": _clean_phrase(raw.get("subject"), 60),
        "action": _clean_phrase(raw.get("action"), 60),
        "environment": _clean_phrase(raw.get("environment"), 60),
        "shotIntent": _clean_phrase(raw.get("shotIntent"), 30),
        "searchQueries": _clean_queries(raw.get("searchQueries"), MAX_QUERIES_PER_PLAN),
        "avoidQueries": _clean_queries(raw.get("avoidQueries"), 4),
    }
    if not plan["searchQueries"] and not plan["subject"]:
        return None
    return plan


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP]


def tokens_match(a: str, b: str) -> bool:
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))


def overlap(query_tokens: list[str], other_tokens: list[str]) -> float:
    """Fraction of `query_tokens` found (prefix-tolerant) in `other_tokens`."""
    if not query_tokens:
        return 0.0
    hits = sum(1 for q in set(query_tokens) if any(tokens_match(q, o) for o in other_tokens))
    return hits / len(set(query_tokens))


# --- Legacy (no semantic metadata) derivation -----------------------------

_STOP_FR_EN = _STOP | {
    "dans", "avec", "sans", "pour", "sous", "sur", "une", "des", "les", "qui", "que", "est", "son", "ses",
    "aux", "par", "pose", "posee", "devant", "chez", "entre", "vers", "tres", "plus", "leur", "leurs",
    "is", "are", "was", "that", "this", "it", "as", "be", "into", "while", "his", "her",
    "fait", "faire", "personne", "gens", "chose", "quelqu", "someone", "person", "people", "thing",
}


def legacy_plan(block: dict, niche: str | None = None) -> dict:
    """Best deterministic plan for a script with no `stockPlan`: keywords of
    the `visual` text (else narration), WITHOUT the old niche-word pollution.
    `legacy=True` tells selection not to enforce slug relevance (the query may
    not be in the library's language, so an absent overlap proves nothing)."""
    text = str(block.get("visual") or "").strip() or str(block.get("text") or "")
    words: list[str] = []
    for w in _TOKEN_RE.findall(text.lower()):
        if len(w) >= 4 and w not in _STOP_FR_EN and w not in words:
            words.append(w)
    queries = []
    if words:
        queries.append(" ".join(words[:4]))
        if len(words) > 2:
            queries.append(" ".join(words[:2]))
    niche_word = (niche or "").replace("-", " ").strip().split(" ")[0] if niche else ""
    if niche_word and words:
        queries.append(f"{words[0]} {niche_word}")
    queries = _clean_queries(queries, MAX_QUERIES_PER_PLAN) or ["people lifestyle"]
    return {
        "visualConcept": text[:120], "subject": "", "action": "", "environment": "",
        "shotIntent": str(block.get("visualPurpose") or ""),
        "searchQueries": queries, "avoidQueries": [], "legacy": True,
    }


# --- Query ladder ---------------------------------------------------------

def build_ladder(plan: dict) -> list[str]:
    """Deterministic ordered search ladder, most specific first, deduplicated,
    capped at MAX_QUERIES_PER_PLAN:
      Q1 specific semantic query  ->  subject+action  ->  next planned query
      ->  subject+environment  ->  visualConcept (broad)  ->  remaining queries.
    """
    sq = list(plan.get("searchQueries") or [])
    subject, action, env = plan.get("subject", ""), plan.get("action", ""), plan.get("environment", "")
    ordered: list[str] = []
    if sq:
        ordered.append(sq[0])
    if subject and action:
        ordered.append(f"{subject} {action}")
    if len(sq) > 1:
        ordered.append(sq[1])
    if subject and env:
        ordered.append(f"{subject} {env}")
    concept = plan.get("visualConcept", "")
    if concept and len(_tokens(concept)) <= 8:
        ordered.append(concept)
    ordered.extend(sq[2:])
    if subject:
        ordered.append(subject)
    return _clean_queries(ordered, MAX_QUERIES_PER_PLAN)


# --- Pexels candidate normalization + file choice --------------------------

def _slug(url: str) -> str:
    m = re.search(r"/video/([^/?#]+)/?", url or "")
    if not m:
        return ""
    return re.sub(r"-\d+$", "", m.group(1))


def pick_file(video: dict, target_w: int = 1080, target_h: int = 1920) -> dict | None:
    """Smallest mp4 that still covers the 1080x1920 frame without upscaling
    (cover-crop scale factor <= 1), else the largest available."""
    files = [f for f in (video.get("video_files") or [])
             if f.get("file_type") == "video/mp4" and f.get("link") and f.get("width") and f.get("height")]
    if not files:
        return None

    def upscale(f: dict) -> float:
        return max(target_w / f["width"], target_h / f["height"])

    sharp = [f for f in files if upscale(f) <= 1.0]
    if sharp:
        return min(sharp, key=lambda f: f["width"] * f["height"])
    return max(files, key=lambda f: f["width"] * f["height"])


def normalize_pexels_video(raw: dict, rank: int = 0) -> dict | None:
    """Compact candidate from a Pexels /videos/search item (real metadata
    only; the raw payload is never kept)."""
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    duration = float(raw.get("duration") or 0)
    if not (3 <= duration <= 30):
        return None
    chosen = pick_file(raw)
    if not chosen:
        return None
    w, h = int(chosen["width"]), int(chosen["height"])
    return {
        "id": str(raw["id"]),
        "width": w, "height": h,
        "duration": duration,
        "url": chosen["link"],
        "slug": _slug(str(raw.get("url") or "")),
        "creator": str((raw.get("user") or {}).get("id") or (raw.get("user") or {}).get("name") or ""),
        "rank": rank,
    }


# --- Ranking --------------------------------------------------------------

@dataclass
class SelectionState:
    """Diversity memory for ONE video, updated as blocks are chosen."""
    used_ids: set = field(default_factory=set)
    used_slug_tokens: list = field(default_factory=list)
    prev_id: str | None = None
    prev_creator: str | None = None
    prev_slug_tokens: list = field(default_factory=list)

    def record(self, cand: dict) -> None:
        toks = _tokens(cand.get("slug", "").replace("-", " "))
        self.used_ids.add(cand["id"])
        self.used_slug_tokens.append(toks)
        self.prev_id, self.prev_creator, self.prev_slug_tokens = cand["id"], cand.get("creator"), toks

    def forget_previous(self) -> None:
        self.prev_id = None
        self.prev_creator = None
        self.prev_slug_tokens = []


def aspect_score(width: int, height: int) -> float:
    """Vertical suitability: 9:16 ideal; landscape loses ~68% of its width to
    the cover-crop, so it is penalised rather than distorted."""
    if not width or not height:
        return -1.5
    r = height / width
    if r >= 1.6:
        return 3.0
    if r >= 1.2:
        return 2.0
    if r >= 0.95:
        return 0.5
    return -1.5


def resolution_score(width: int, height: int) -> float:
    """Sharpness after the cover-crop to 1080x1920 (upscale factor)."""
    if not width or not height:
        return -1.0
    u = max(1080 / width, 1920 / height)
    if u <= 1.0:
        return 1.0
    if u <= 1.5:
        return 0.3
    return -1.0


def duration_score(clip_seconds: float, block_seconds: float) -> float:
    """`video._render_block_clip` LOOPS clips shorter than the block."""
    if clip_seconds >= block_seconds:
        return 1.0
    if clip_seconds >= 0.6 * block_seconds:
        return 0.3
    return -0.8


def rank_candidates(
    candidates: list[dict], *, query: str, level: int, plan: dict, block: dict,
    state: SelectionState, block_seconds: float,
) -> list[dict]:
    """Scored copies of `candidates`, best first (ties keep Pexels order)."""
    q_tokens = _tokens(query)
    plan_tokens = _tokens(f"{plan.get('subject', '')} {plan.get('action', '')}")
    avoid_tokens = [t for t in _tokens(" ".join(plan.get("avoidQueries") or [])) if t not in q_tokens]
    hints = _SHOT_SLUG_HINTS.get(str(block.get("shotType") or ""), set())
    level_bonus = _LEVEL_BONUS[min(level, len(_LEVEL_BONUS) - 1)]
    n = max(len(candidates), 1)
    ranked = []
    for idx, c in enumerate(candidates):
        slug_tokens = _tokens(c.get("slug", "").replace("-", " "))
        relevance = 0.7 * overlap(q_tokens, slug_tokens) + 0.3 * overlap(plan_tokens, slug_tokens) if plan_tokens \
            else overlap(q_tokens, slug_tokens)
        parts = {
            "aspect": aspect_score(c["width"], c["height"]),
            "resolution": resolution_score(c["width"], c["height"]),
            "duration": duration_score(c["duration"], block_seconds),
            "relevance": round(4.0 * relevance, 3),
            "queryLevel": level_bonus,
            "pexelsRank": round(0.3 * (1 - idx / n), 3),
            "shotHint": _SHOT_HINT_BONUS if hints and any(tokens_match(h, t) for h in hints for t in slug_tokens) else 0.0,
        }
        avoid_hits = sum(1 for a in set(avoid_tokens) if any(tokens_match(a, t) for t in slug_tokens))
        non_footage = any(tokens_match(n, t) for n in _NON_FOOTAGE_TOKENS - set(q_tokens) for t in slug_tokens)
        penalties = {
            "avoid": -min(_AVOID_PENALTY * avoid_hits, _AVOID_PENALTY_CAP),
            "nonFootage": -_NON_FOOTAGE_PENALTY if non_footage else 0.0,
            "duplicate": -_DUPLICATE_PENALTY if c["id"] in state.used_ids else 0.0,
            "consecutive": -_CONSECUTIVE_PENALTY if c["id"] == state.prev_id else 0.0,
            "sameCreator": -_SAME_CREATOR_PENALTY if c.get("creator") and c.get("creator") == state.prev_creator else 0.0,
            "repeatPrev": -round(_PREV_REPEAT_WEIGHT * overlap(slug_tokens, state.prev_slug_tokens), 3),
            "repeatAny": -round(_ANY_REPEAT_WEIGHT * max(
                (overlap(slug_tokens, prev) for prev in state.used_slug_tokens), default=0.0), 3),
        }
        score = round(sum(parts.values()) + sum(penalties.values()), 3)
        ranked.append({
            **c, "score": score, "relevance": round(relevance, 3), "level": level, "query": query,
            "pexelsIndex": idx,
            "duplicatePenalty": round(penalties["duplicate"] + penalties["consecutive"], 2),
            "breakdown": {**parts, **penalties},
        })
    ranked.sort(key=lambda c: (-c["score"], c["pexelsIndex"]))
    return ranked


# --- Selection over the ladder --------------------------------------------

SearchFn = Callable[[str, str | None], list]  # (query, orientation|None) -> normalized candidates
DownloadFn = Callable[[str, str], None]


def _accepts(cand: dict, legacy: bool) -> bool:
    if cand["duplicatePenalty"] < 0:
        return False
    if cand["score"] < ACCEPT_SCORE:
        return False
    return legacy or cand["relevance"] >= ACCEPT_RELEVANCE


def choose_for_block(
    plan: dict, block: dict, state: SelectionState, search_fn: SearchFn, block_seconds: float,
    orientation: str = "portrait",
) -> tuple[dict | None, dict]:
    """Walks the ladder. Returns (chosen candidate | None, per-block report
    fragment). The caller downloads and records the chosen clip."""
    ladder = build_ladder(plan)
    legacy = bool(plan.get("legacy"))
    attempted: list[str] = []
    seen_ids: set[str] = set()
    searches = 0
    best_available: dict | None = None
    chosen: dict | None = None
    chosen_how = "none"

    for level, query in enumerate(ladder):
        if searches >= MAX_SEARCHES_PER_BLOCK:
            break
        attempted.append(query)
        pool = list(search_fn(query, orientation) or [])
        searches += 1
        if orientation == "portrait" and len(pool) < MIN_PORTRAIT_POOL and searches < MAX_SEARCHES_PER_BLOCK:
            extra = search_fn(query, None) or []
            searches += 1
            have = {c["id"] for c in pool}
            pool += [c for c in extra if c["id"] not in have]
        for c in pool:
            seen_ids.add(c["id"])
        if not pool:
            continue
        ranked = rank_candidates(
            pool, query=query, level=level, plan=plan, block=block, state=state, block_seconds=block_seconds,
        )
        for cand in ranked:
            if _accepts(cand, legacy):
                chosen, chosen_how = cand, "ladder"
                break
        if chosen:
            break
        for cand in ranked:
            # Fallback pool: no consecutive repeat ever; a duplicate only if nothing else exists.
            if cand["id"] == state.prev_id:
                continue
            if cand["pexelsIndex"] < LOW_CONFIDENCE_MAX_RANK and level <= 1 or legacy:
                if best_available is None or cand["score"] > best_available["score"]:
                    best_available = cand
                break

    if chosen is None and best_available is not None:
        chosen, chosen_how = best_available, "best_available"

    report = {
        "queriesAttempted": attempted,
        "searches": searches,
        "candidateCount": len(seen_ids),
        "fallback": chosen_how if chosen else "none",
    }
    return chosen, report


def select_stock_clips(
    blocks: list[dict],
    plans: list[dict],
    *,
    images_dir: Path,
    search_fn: SearchFn,
    download_fn: DownloadFn,
    photo_fn: Callable[[str, Path], str | None] | None = None,
    durations: list[float] | None = None,
    orientation: str = "portrait",
    exists_fn: Callable[[Path], bool] | None = None,
) -> tuple[list[str | None], list[dict]]:
    """One clip path (or None) per block + one metrics entry per block.
    Sequential on purpose: each choice depends on the diversity state."""
    exists = exists_fn or (lambda p: p.exists() and p.stat().st_size > 0)
    cached_report = _load_report(images_dir)
    state = SelectionState()
    paths: list[str | None] = [None] * len(blocks)
    reports: list[dict] = []

    for i, block in enumerate(blocks):
        plan = plans[i]
        base = {
            "blockIndex": i,
            "visualConcept": plan.get("visualConcept", ""),
            "planSource": plan.get("source", "legacy"),
            "shotType": block.get("shotType"),
            "visualPurpose": block.get("visualPurpose"),
        }
        if i > 0 and block.get("reuse_visual_from_previous"):
            paths[i] = paths[i - 1]
            reports.append({**base, "fallback": "reused_previous", "queriesAttempted": [], "searches": 0})
            continue
        video_path = images_dir / f"block-{i + 1:02d}.mp4"
        photo_path = images_dir / f"block-{i + 1:02d}.jpg"
        cached = next((p for p in (video_path, photo_path) if exists(p)), None)
        if cached is not None:
            paths[i] = str(cached)
            prior = cached_report.get(str(i)) or {}
            reports.append({**base, **prior, "cached": True})
            if prior.get("selectedAssetId"):
                state.record({"id": prior["selectedAssetId"], "slug": prior.get("selectedSlug", ""),
                              "creator": prior.get("creator")})
            continue

        block_seconds = float(durations[i]) if durations and i < len(durations) and durations[i] else _DEFAULT_BLOCK_SECONDS
        chosen, frag = choose_for_block(plan, block, state, search_fn, block_seconds, orientation)
        entry = {**base, **frag, "selectedQuery": None, "selectedAssetId": None, "selectedAspectRatio": None,
                 "selectionScore": None, "fallbackLevel": None, "duplicatePenalty": 0.0}
        if chosen:
            try:
                download_fn(chosen["url"], str(video_path))
                paths[i] = str(video_path)
                state.record(chosen)
                entry.update({
                    "selectedQuery": chosen["query"], "selectedAssetId": chosen["id"],
                    "selectedAspectRatio": round(chosen["width"] / chosen["height"], 3),
                    "selectedSize": f"{chosen['width']}x{chosen['height']}",
                    "selectedDuration": chosen["duration"], "selectedSlug": chosen["slug"], "creator": chosen.get("creator"),
                    "selectionScore": chosen["score"], "fallbackLevel": chosen["level"],
                    "relevance": chosen["relevance"], "duplicatePenalty": chosen["duplicatePenalty"],
                    "scoreBreakdown": {k: v for k, v in chosen["breakdown"].items() if v},
                    "lowConfidence": frag["fallback"] == "best_available",
                })
            except (requests.RequestException, OSError):
                entry["fallback"] = "download_failed"
                chosen = None
        if not chosen and photo_fn is not None:
            ladder = build_ladder(plan)
            photo = photo_fn(ladder[-1] if ladder else "", photo_path) if ladder else None
            if photo:
                paths[i] = photo
                entry["fallback"] = "photo"
                entry["selectedQuery"] = ladder[-1]
                entry["searches"] = entry.get("searches", 0) + 1
                state.forget_previous()
        if paths[i] is None:
            entry["fallback"] = "flat_color"
            state.forget_previous()
        reports.append(entry)

    _store_report(images_dir, reports)
    return paths, reports


# --- Report persistence (cache hits keep their original provenance) --------

_REPORT_NAME = "stock-report.json"


def _load_report(images_dir: Path) -> dict:
    try:
        rows = json.loads((images_dir / _REPORT_NAME).read_text(encoding="utf-8"))
        return {str(r["blockIndex"]): r for r in rows if isinstance(r, dict) and "blockIndex" in r}
    except (OSError, ValueError, KeyError):
        return {}


def _store_report(images_dir: Path, reports: list[dict]) -> None:
    try:
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / _REPORT_NAME).write_text(json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


# --- Planning (ONE call per video) -----------------------------------------

def planner_model() -> str | None:
    if os.environ.get("STOCK_PLANNER", "").strip().lower() in {"off", "0", "false"}:
        return None
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return (os.environ.get("STOCK_PLANNER_MODEL") or os.environ.get("ORIGINALITY_MODEL") or "").strip() or None


def build_planning_messages(blocks: list[dict], niche: str | None, language: str | None) -> list[dict]:
    rows = []
    for i, b in enumerate(blocks, 1):
        rows.append({
            "index": i,
            "role": b.get("role"),
            "narration": str(b.get("text") or "")[:400],
            "visualIdea": str(b.get("visual") or "")[:300],
            "shotType": b.get("shotType"),
            "shotGuidance": SHOT_GUIDANCE.get(str(b.get("shotType") or "")),
            "visualPurpose": b.get("visualPurpose"),
            "purposeGuidance": PURPOSE_GUIDANCE.get(str(b.get("visualPurpose") or "")),
        })
    system = (
        "You are a B-roll editor planning STOCK FOOTAGE searches (Pexels video) for a vertical short video. "
        "Separate what the narration SAYS from what the viewer should SEE: choose concrete, filmable visual "
        "evidence (people, objects, places, actions), never an abstract idea, never charts or readable numbers. "
        "For every block return: visualConcept (one sentence), subject, action, environment (short phrases), "
        "shotIntent, searchQueries (3 queries, 2-5 words each, ordered most specific to broader, everyday stock-library "
        "vocabulary), avoidQueries (2-4 things a naive search would wrongly return, e.g. 'stock market chart'). "
        "ALL search text MUST be in English whatever the narration language. "
        "Respect shotGuidance/purposeGuidance. The blocks form one sequence: consecutive blocks must differ in subject, "
        "setting or action and the images should progress with the story; never reuse a query. "
        "The visualIdea is the author's intent: keep it if it is filmable, rewrite it if a stock library could not "
        'show it. Reply with JSON only: {"blocks":[{"index":1,"visualConcept":"","subject":"","action":"",'
        '"environment":"","shotIntent":"","searchQueries":[],"avoidQueries":[]}]}'
    )
    user = json.dumps({"niche": niche, "narrationLanguage": language or "unknown", "blocks": rows}, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_planning_response(content: str, n_blocks: int) -> dict[int, dict]:
    """{0-based block index: normalized plan} for every block the model planned
    validly; silently drops the rest (they fall back to the legacy plan)."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return {}
    rows = data.get("blocks") if isinstance(data, dict) else None
    out: dict[int, dict] = {}
    for row in rows or []:
        try:
            idx = int(row.get("index")) - 1
        except (AttributeError, TypeError, ValueError):
            continue
        plan = normalize_plan(row)
        if plan and 0 <= idx < n_blocks:
            out[idx] = plan
    return out


def _call_planner(messages: list[dict], model: str) -> tuple[str, dict]:
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "response_format": {"type": "json_object"}, "messages": messages},
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    return body["choices"][0]["message"]["content"], {
        "input": int(usage.get("prompt_tokens") or 0), "output": int(usage.get("completion_tokens") or 0),
    }


def _plan_cache_key(blocks: list[dict], niche: str | None, language: str | None, model: str) -> str:
    payload = json.dumps(
        {"v": PLAN_VERSION, "model": model, "niche": niche, "language": language,
         "blocks": [[b.get("text"), b.get("visual"), b.get("shotType"), b.get("visualPurpose")] for b in blocks]},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def plan_blocks(
    blocks: list[dict],
    niche: str | None,
    language: str | None,
    work_dir: Path | None = None,
    *,
    call_fn: Callable[[list[dict], str], tuple[str, dict]] | None = None,
) -> tuple[list[dict], dict]:
    """One plan per block + a planning summary (source counts, LLM calls, token
    usage, latency, errors). At most ONE LLM call for the whole video, and none
    when every block already carries a `stockPlan`, no model is configured, or
    the cached plan matches. Every failure degrades to `legacy_plan`."""
    plans: list[dict | None] = []
    for b in blocks:
        p = normalize_plan(b.get("stockPlan")) if isinstance(b, dict) else None
        plans.append({**p, "source": "script"} if p else None)
    summary = {"llmCalls": 0, "tokens": None, "seconds": 0.0, "model": None, "error": None, "cached": False}

    missing = [i for i, p in enumerate(plans) if p is None]
    model = planner_model()
    if missing and model:
        summary["model"] = model
        cache_path = Path(work_dir) / "images" / "stock-plan.json" if work_dir else None
        key = _plan_cache_key(blocks, niche, language, model)
        llm_plans: dict[int, dict] = {}
        if cache_path and cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("key") == key:
                    llm_plans = {int(k): v for k, v in cached["plans"].items()}
                    summary["cached"] = True
            except (OSError, ValueError, KeyError):
                llm_plans = {}
        if not llm_plans:
            t0 = time.monotonic()
            try:
                content, usage = (call_fn or _call_planner)(build_planning_messages(blocks, niche, language), model)
                summary["llmCalls"] = 1
                summary["tokens"] = usage
                llm_plans = parse_planning_response(content, len(blocks))
                if cache_path and llm_plans:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(
                        json.dumps({"key": key, "plans": {str(k): v for k, v in llm_plans.items()}}, ensure_ascii=False),
                        encoding="utf-8",
                    )
            except (requests.RequestException, KeyError, ValueError, IndexError, OSError) as exc:
                summary["error"] = str(exc)[:160]
            summary["seconds"] = round(time.monotonic() - t0, 2)
        for i in missing:
            if i in llm_plans:
                plans[i] = {**llm_plans[i], "source": "llm"}

    for i, p in enumerate(plans):
        if p is None:
            plans[i] = {**legacy_plan(blocks[i], niche), "source": "legacy"}
    summary["sources"] = {s: sum(1 for p in plans if p["source"] == s) for s in ("script", "llm", "legacy")}
    return plans, summary  # type: ignore[return-value]
