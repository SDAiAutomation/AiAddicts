"""Beat direction for the storyboard renderer: ONE model call per story says, for every beat, what the picture must show.

The prompt is versioned, the model is replaceable (any caller with the `call(messages, model) -> (text, usage)` shape,
by default OpenAI chat completions, already used by the Standard stock planner) and the answer is never trusted: closed
enums, bounded counts and lengths, known character ids only. Anything invalid is repaired field by field, and a missing
or unusable answer falls back to a deterministic direction, so a model failure never fails the video. Nothing from the
answer is ever used as a path, a URL or a command: `show` only becomes part of an image prompt.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable

import requests

PROMPT_VERSION = "storyboard-direction/1.0.0"
CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5-mini"

SHOT_SIZES = ("wide", "medium", "close_up", "insert")
CAMERA_MOVES = ("push_in", "pull_out", "pan_left", "pan_right", "static", "shake")
# generic, style-consistent extras (the references use "types", not recurring individuals); id -> what to draw
CROWD_TYPES = {
    "worker": "ouvrier à casquette plate et bretelles",
    "boss": "patron ventru en haut-de-forme et cigare",
    "banker": "banquier à moustache en costume trois pièces",
    "policeman": "agent de police à casque et matraque",
    "shopkeeper": "commerçant en tablier",
    "passerby": "passant anonyme en manteau et chapeau mou",
    "journalist": "reporter à chapeau avec carte de presse, appareil photo à flash",
    "child": "enfant en culottes courtes et casquette",
    "elder": "vieil homme à canne et lunettes",
    "lady": "dame élégante à chapeau cloche",
    "crowd": "foule de silhouettes cartoon toutes différentes",
}
MAX_CHARACTERS_PER_BEAT = 3
MAX_CROWD_PER_BEAT = 3
SHOW_MIN, SHOW_MAX = 8, 300
MAX_ATTEMPTS = 2
MAX_SECTION_RATE = 4           # at most one section change every 4 beats
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")
_FALLBACK_SIZES = ("wide", "close_up", "medium", "insert")
_FALLBACK_MOVES = ("push_in", "pan_left", "pull_out", "pan_right")


@dataclass
class Direction:
    beats: list                         # one dict per beat: show, shot, camera, characters, crowd, section_start, source
    source: str                         # "llm" | "mixed" | "fallback"
    llm_calls: int = 0
    usage: list = field(default_factory=list)   # [{"input", "output"}] per call, as reported by the provider
    errors: list = field(default_factory=list)  # short diagnostics, never the prompt


def director_model() -> str | None:
    """None when no model can be called (no key on this worker): the deterministic direction is used."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return (os.environ.get("STORY_DIRECTOR_MODEL") or os.environ.get("ORIGINALITY_MODEL") or "").strip() or DEFAULT_MODEL


def call_openai(messages: list, model: str) -> tuple[str, dict]:
    """The only network call of this module (tests always replace it)."""
    resp = requests.post(
        CHAT_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "response_format": {"type": "json_object"}, "messages": messages},
        timeout=180,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    return body["choices"][0]["message"]["content"], {
        "input": int(usage.get("prompt_tokens") or 0), "output": int(usage.get("completion_tokens") or 0)}


def clean_text(value, limit: int = SHOW_MAX) -> str:
    """Printable, single-spaced, bounded text ('' when not a string)."""
    if not isinstance(value, str):
        return ""
    return _SPACES.sub(" ", _CONTROL.sub(" ", value)).strip()[:limit]


def build_messages(story: dict, beats: list, looks: dict, title: str | None = None) -> list:
    """`looks`: character id -> {"name", "description"} of the recurring characters (the narrator has no body)."""
    shots = story.get("shots") or []
    rows = []
    for b in beats:
        shot = shots[b["shot_index"]] if 0 <= b.get("shot_index", -1) < len(shots) else {}
        rows.append({
            "i": b["index"], "phrase": b["text"][:400],
            "speaker": b.get("speaker_id") if b.get("speaker_id") in looks else "narrator",
            "line_context": str(shot.get("dialogue") or "")[:400] if b.get("line_first") else None,
            "author_intent": clean_text(shot.get("intent"), 200) or None,
        })
    system = (
        "You are the storyboard director of a vertical animated short (9:16), drawn as ONE still image per beat that the "
        "editor animates with a camera move. Each beat is 2-4 seconds of narration. For EVERY beat, decide the single image "
        "that makes THIS exact phrase visible.\n"
        "Rules:\n"
        "- One idea = one image. Show the concrete action, object or place the phrase names (if the phrase says someone "
        "takes out a phone, show the hand pulling out the phone; if everyone steps back, show the crowd stepping back).\n"
        "- Abstract ideas become visual metaphors; objects may have expressive cartoon faces (a worried clock, a greedy safe).\n"
        "- Vary the framing like an editor: establishing wide shots, medium shots, close-ups on faces, inserts on objects. "
        "Never more than two identical shot sizes in a row; at least a third of the beats are close_up or insert.\n"
        "- When a recurring character speaks, show them acting the line (close_up or medium). Recurring characters are "
        "referred to ONLY by their id in `characters`; never describe their look, it is fixed elsewhere.\n"
        "- Background people are generic types from this list only: " + ", ".join(CROWD_TYPES) + ".\n"
        "- Never ask for written words, letters, numbers, signs, captions or logos in the image.\n"
        "- `show`: one English sentence (10-45 words), concrete and drawable, present tense, no camera jargon.\n"
        "- `camera`: push_in (tension, revelation), pull_out (reveal context), pan_left / pan_right (travel, crowd), "
        "static (calm), shake (shock, panic; rare).\n"
        "- `section_start`: true only where the story clearly changes time, place or section (rare).\n"
        'Reply with JSON only: {"beats":[{"i":0,"show":"","shot":"wide|medium|close_up|insert",'
        '"camera":"push_in|pull_out|pan_left|pan_right|static|shake","characters":[],"crowd":[],"section_start":false}]}'
    )
    user = json.dumps({
        "prompt_version": PROMPT_VERSION, "title": clean_text(title, 120) or None,
        "language": story.get("language", "fr"), "style": story.get("style_id"),
        "characters": [{"id": cid, "name": look["name"]} for cid, look in looks.items()],
        "beats": rows,
    }, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse(content) -> list | None:
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        try:
            data = json.loads(content[content.index("{"): content.rindex("}") + 1])
        except ValueError:
            return None
    rows = data.get("beats") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else None


def fallback_beat(beat: dict, looks: dict) -> dict:
    """Deterministic direction from the phrase itself (no model)."""
    i = beat["index"]
    speaker = beat.get("speaker_id") if beat.get("speaker_id") in looks else None
    phrase = clean_text(beat.get("text"), 220)
    if speaker:
        show = f"{looks[speaker]['name']} says, with an expressive face and a clear gesture: “{phrase}”"
        shot = ("close_up", "medium")[i % 2]
    else:
        show = f"A single clear image that literally shows: “{phrase}”"
        shot = _FALLBACK_SIZES[i % len(_FALLBACK_SIZES)] if i else "wide"
    return {"show": show[:SHOW_MAX], "shot": shot, "camera": _FALLBACK_MOVES[i % len(_FALLBACK_MOVES)],
            "characters": [speaker] if speaker else [], "crowd": [], "section_start": False, "source": "fallback"}


def validate_row(row, beat: dict, looks: dict) -> tuple[dict, int]:
    """(repaired direction, number of repaired fields). An invalid `show` makes the whole beat fall back."""
    base = fallback_beat(beat, looks)
    if not isinstance(row, dict):
        return base, 1
    show = clean_text(row.get("show"))
    if len(show) < SHOW_MIN:
        return base, 1
    repaired = 0
    out = {"show": show, "source": "llm"}
    if row.get("shot") in SHOT_SIZES:
        out["shot"] = row["shot"]
    else:
        out["shot"], repaired = base["shot"], repaired + 1
    if row.get("camera") in CAMERA_MOVES:
        out["camera"] = row["camera"]
    else:
        out["camera"], repaired = base["camera"], repaired + 1
    chars = row.get("characters", [])
    if not isinstance(chars, list):
        chars, repaired = [], repaired + 1
    known = [c for c in chars if isinstance(c, str) and c in looks]
    repaired += len(known) != len(chars)
    out["characters"] = list(dict.fromkeys(known))[:MAX_CHARACTERS_PER_BEAT]
    crowd = row.get("crowd", [])
    if not isinstance(crowd, list):
        crowd, repaired = [], repaired + 1
    kept = [c for c in crowd if isinstance(c, str) and c in CROWD_TYPES]
    repaired += len(kept) != len(crowd)
    out["crowd"] = list(dict.fromkeys(kept))[:MAX_CROWD_PER_BEAT]
    out["section_start"] = row.get("section_start") is True
    return out, repaired


def enforce_variety(directions: list) -> list:
    """No three identical shot sizes in a row, no identical camera move twice in a row, sparse section changes, never a
    section change on the first beat. Deterministic."""
    out = [dict(d) for d in directions]
    last_section = -MAX_SECTION_RATE
    for i, d in enumerate(out):
        if i >= 2 and d["shot"] == out[i - 1]["shot"] == out[i - 2]["shot"]:
            d["shot"] = next(s for s in ("close_up", "insert", "medium", "wide") if s != d["shot"])
        if i >= 1 and d["camera"] == out[i - 1]["camera"] and d["camera"] != "static":
            d["camera"] = next(m for m in _FALLBACK_MOVES if m != d["camera"])
        if d["section_start"]:
            if i == 0 or i - last_section < MAX_SECTION_RATE:
                d["section_start"] = False
            else:
                last_section = i
    return out


def direct(story: dict, beats: list, looks: dict, *, call: Callable | None, model: str | None,
           title: str | None = None, attempts: int = MAX_ATTEMPTS) -> Direction:
    """Direction for every beat. `call=None` or `model=None` -> deterministic direction, no paid call."""
    result = Direction(beats=[], source="fallback")
    rows_by_index: dict[int, object] = {}
    if call is not None and model:
        messages = build_messages(story, beats, looks, title)
        for _ in range(max(1, min(attempts, MAX_ATTEMPTS))):
            result.llm_calls += 1
            try:
                content, usage = call(messages, model)
            except (requests.RequestException, KeyError, ValueError, IndexError, TypeError, OSError) as exc:
                result.errors.append(f"call failed: {type(exc).__name__}")
                continue
            if isinstance(usage, dict):
                result.usage.append({"input": int(usage.get("input") or 0), "output": int(usage.get("output") or 0)})
            rows = _parse(content)
            if rows is None:
                result.errors.append("answer is not the expected JSON")
                continue
            for row in rows:
                idx = row.get("i") if isinstance(row, dict) else None
                if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(beats) and idx not in rows_by_index:
                    rows_by_index[idx] = row
            break
    directions, from_llm = [], 0
    for b in beats:
        if b["index"] in rows_by_index:
            d, _ = validate_row(rows_by_index[b["index"]], b, looks)
        else:
            d = fallback_beat(b, looks)
        from_llm += d["source"] == "llm"
        directions.append(d)
    result.beats = enforce_variety(directions)
    result.source = "llm" if from_llm == len(beats) else "mixed" if from_llm else "fallback"
    return result


def llm_cost_usd(usage: list) -> float | None:
    """Cost from reported tokens and env prices ($ per million: STORY_DIRECTOR_PRICE_IN_PER_M / _OUT_PER_M); None when a
    price is not configured (never guessed)."""
    try:
        p_in = float(os.environ["STORY_DIRECTOR_PRICE_IN_PER_M"])
        p_out = float(os.environ["STORY_DIRECTOR_PRICE_OUT_PER_M"])
    except (KeyError, ValueError):
        return None
    return round(sum(u["input"] * p_in + u["output"] * p_out for u in usage) / 1e6, 5)
