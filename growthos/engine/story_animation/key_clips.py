"""Key clips: turn the 3-5 beats of a story that most need motion into short image-to-video clips.

Standalone and OFF by default. Nothing here is wired into the worker or the renderer: the storyboard renderer
(one still per 2-4 s beat with a camera move) calls `make_key_clips` and, for every beat whose entry in
`KeyClipsReport.clips` is a path, plays that clip instead of the still. Any failure leaves the entry at None and
the renderer keeps the still image, so a story never fails because of a key clip.

Beat shape expected from the renderer (adapt there, not here):

    Beat(id="b07", start=12.4, end=15.6, text="Les patrons secouent la grille.",
         intent="conflict", description="three bosses shake the factory gate with their whole body",
         image_path="/work/story/beats/b07.png", motion=None)

- id: [A-Za-z0-9_-]{1,64}, used to name the output file (never a user path).
- start/end: seconds on the narration timeline; end > start.
- text: the narration line of the beat; description: the visual description used for the still.
- intent: free text (hook, setup, conflict, climax, reveal, resolution, ...) from the beat direction.
- image_path: the still already generated for the beat (png/jpg/webp); None means not eligible.
- motion: explicit author/direction flag; True forces the beat into the candidates, False excludes it,
  None lets the heuristic decide.

Provider choice: env `STORY_KEY_CLIP_PROVIDER` (empty = disabled). Only `fake` works today; `veo`, `seedance`
and `wan` are stubs raising NotConfigured until the owner picks one (see
docs/product/STORY_STUDIO_KEY_CLIPS_2026-10-28.md). No endpoint is guessed here.

Costs: every attempt records an estimated cost (requested seconds x per-second rate) and the actual cost reported
by the provider, separately. A missing actual cost is None (unknown), never 0. The per-story cap
(`STORY_KEY_CLIP_MAX_USD`, default 1.5) is checked before every attempt, retries included, against the committed
spend (actual when reported, otherwise the estimate).
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from . import quality

KEY_CLIPS_VERSION = "story-key-clips:v1"
MOTION_PROMPT_VERSION = "key-clip-motion:v1"

ENV_PROVIDER = "STORY_KEY_CLIP_PROVIDER"
ENV_MAX_USD = "STORY_KEY_CLIP_MAX_USD"
ENV_MAX_CLIPS = "STORY_KEY_CLIP_MAX_CLIPS"
ENV_TIMEOUT_S = "STORY_KEY_CLIP_TIMEOUT_S"
ENV_USD_PER_S = "STORY_KEY_CLIP_USD_PER_S"

DEFAULT_MAX_USD = 1.5
ABSOLUTE_MAX_USD = 10.0          # a typo in the env never authorises more than this per story
DEFAULT_MAX_CLIPS = 4
MAX_CLIPS_LIMIT = 5
DEFAULT_MAX_TOTAL_S = 18.0       # total requested seconds of motion per story
DEFAULT_TIMEOUT_S = 300.0
MAX_ATTEMPTS = 2                 # first try + one retry, never more

MIN_CLIP_S = 1.5                 # shorter beats are not worth a clip
MAX_CLIP_S = 5.0                 # longer beats get a 5 s clip; the renderer holds the last frame or trims
ASPECT = "9:16"
ASPECT_RATIO = 9 / 16
ASPECT_TOLERANCE = 0.03
MIN_WIDTH = 480
MAX_BLACK_FRACTION = 0.5
MAX_FROZEN_FRACTION = 0.5
DURATION_TOLERANCE_S = 0.15

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class KeyClipError(RuntimeError):
    """A key clip attempt failed; the caller keeps the still image."""


class NotConfigured(KeyClipError):
    """The selected provider has no endpoint, key or price chosen by the owner yet."""


class UnknownProvider(KeyClipError):
    """`STORY_KEY_CLIP_PROVIDER` names a provider this module does not know."""


# --------------------------------------------------------------------------- beats


@dataclass(frozen=True)
class Beat:
    id: str
    start: float
    end: float
    text: str = ""
    intent: str = ""
    description: str = ""
    image_path: str | None = None
    motion: bool | None = None

    @property
    def duration_s(self) -> float:
        return max(0.0, float(self.end) - float(self.start))

    @classmethod
    def from_dict(cls, data: Mapping) -> "Beat":
        motion = data.get("motion")
        return cls(
            id=str(data.get("id", "")),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=str(data.get("text") or ""),
            intent=str(data.get("intent") or ""),
            description=str(data.get("description") or ""),
            image_path=str(data["image_path"]) if data.get("image_path") else None,
            motion=motion if isinstance(motion, bool) else None,
        )


def _as_beat(b) -> Beat:
    return b if isinstance(b, Beat) else Beat.from_dict(b)


# Small, auditable vocabulary (EN + FR). Keyword matching is not story comprehension: it only ranks.
_INTENT_WEIGHTS = (
    (re.compile(r"\b(climax|apog[ée]e|paroxysm)\w*", re.I), 5),
    (re.compile(r"\b(conflict|confront|fight|chase|clash|conflit|affront|bagarre|poursuite)\w*", re.I), 4),
    (re.compile(r"\b(action|turn|twist|retournement|bascul)\w*", re.I), 3),
    (re.compile(r"\b(reveal|discover|révél|découvr)\w*", re.I), 2),
)
_ACTION = re.compile(
    r"\b(run|runs|running|ran|jump|jumps|jumping|fall|falls|falling|fell|throw|throws|threw|shake|shakes|shaking|"
    r"push|pushes|pull|pulls|hit|hits|smash|grab|grabs|swing|swings|chase|chases|dance|dances|climb|climbs|"
    r"walk|walks|walking|kick|kicks|spin|spins|slam|slams|pour|pours|wave|waves|fight|fights|explode|explodes|"
    r"court|courent|cour[ts]|saute|sautent|tombe|tombent|lance|lancent|jette|jettent|secoue|secouent|pousse|"
    r"poussent|tire|tirent|frappe|frappent|attrape|attrapent|danse|dansent|grimpe|grimpent|marche|marchent|"
    r"brandit|brandissent|verse|versent|explose|explosent|s'enfuit|s'enfuient|fonce|foncent)\b",
    re.I,
)
_CALM = re.compile(r"\b(calm|still|silence|portrait|title|titre|calme|immobile|fixe)\b", re.I)


def motion_score(beat: Beat) -> int:
    """Deterministic score of how much a beat needs real motion (0 = a still with a camera move is enough)."""
    if beat.motion is True:
        return 100
    if beat.motion is False:
        return 0
    score = 0
    for pattern, weight in _INTENT_WEIGHTS:
        if pattern.search(beat.intent):
            score += weight
    actions = len(_ACTION.findall(f"{beat.description} {beat.text}"))
    score += 2 * min(actions, 3)
    if _CALM.search(beat.intent) or _CALM.search(beat.description):
        score -= 2
    return max(score, 0)


def _eligible(beat: Beat) -> bool:
    return bool(_ID.match(beat.id)) and beat.image_path is not None and beat.duration_s >= MIN_CLIP_S and beat.motion is not False


def clip_seconds(beat: Beat) -> float:
    """Requested clip length: the beat length rounded up to the second, bounded to [2, MAX_CLIP_S]."""
    return float(min(MAX_CLIP_S, max(2.0, math.ceil(beat.duration_s - 1e-6))))


def select_key_beats(beats: Sequence, max_clips: int = DEFAULT_MAX_CLIPS, max_total_s: float = DEFAULT_MAX_TOTAL_S) -> list[Beat]:
    """Choose the beats that most need motion, deterministically.

    Ranking: explicit `motion=True` first, then score (intent climax/conflict/action, action verbs), then earlier
    start, then id. Beats with score 0, no still, an invalid id or shorter than MIN_CLIP_S are never chosen.
    Bounded by `max_clips` (capped at MAX_CLIPS_LIMIT) and by the total requested seconds. Returned in story order.
    """
    max_clips = max(0, min(int(max_clips), MAX_CLIPS_LIMIT))
    candidates = [b for b in map(_as_beat, beats) if _eligible(b)]
    scored = sorted(((motion_score(b), b) for b in candidates), key=lambda sb: (-sb[0], sb[1].start, sb[1].id))
    chosen: list[Beat] = []
    total = 0.0
    for score, beat in scored:
        if len(chosen) >= max_clips:
            break
        if score <= 0:
            break
        seconds = clip_seconds(beat)
        if total + seconds > max_total_s + 1e-9:
            continue
        chosen.append(beat)
        total += seconds
    return sorted(chosen, key=lambda b: (b.start, b.id))


# --------------------------------------------------------------------------- motion prompt


@dataclass(frozen=True)
class Style:
    name: str
    look: str
    accent: str
    identity: str = "Keep every character exactly as drawn in the input image: same design, proportions, outfit and face."
    forbid: str = "No text, no letters, no captions, no subtitles, no logos, no watermark."


STYLE_1930S_RUBBER_HOSE = Style(
    name="rubber_hose_1930s_bw",
    look="1930s rubber hose cartoon, black and white, bouncy tubular limbs, white gloves, pie-cut eyes, light film grain",
    accent="The single red accent of the image stays red and is the only colour; everything else stays black and white.",
)

_CAMERA_ACTION = "Locked-off camera, the characters' full-body acting carries the motion."
_CAMERA_CLIMAX = "Slow push-in toward the main character during the action."
_CAMERA_REVEAL = "Slow push-in that ends on the revealed element."
_CAMERA_DEFAULT = "Gentle, steady camera with a slight drift; no cut."


@dataclass(frozen=True)
class MotionPrompt:
    prompt: str
    negative: str
    camera: str
    version: str = MOTION_PROMPT_VERSION


def _clean(text: str, limit: int) -> str:
    text = _CONTROL.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


def camera_instruction(beat: Beat) -> str:
    intent = beat.intent or ""
    if re.search(r"\b(climax|apog[ée]e)\w*", intent, re.I):
        return _CAMERA_CLIMAX
    if re.search(r"\b(reveal|révél|découvr|discover)\w*", intent, re.I):
        return _CAMERA_REVEAL
    if _ACTION.search(f"{beat.description} {beat.text}") or re.search(r"\b(conflict|action|chase|fight|conflit)\w*", intent, re.I):
        return _CAMERA_ACTION
    return _CAMERA_DEFAULT


def build_motion_prompt(beat, style: Style = STYLE_1930S_RUBBER_HOSE) -> MotionPrompt:
    """Image-to-video prompt: what moves (from the beat description), how it looks, what must not change."""
    beat = _as_beat(beat)
    action = _clean(beat.description, 400) or _clean(beat.text, 300) or "The characters react with lively full-body acting."
    if not action.endswith((".", "!", "?")):
        action += "."
    camera = camera_instruction(beat)
    prompt = " ".join([
        f"Animate this still: {action}",
        "Full-body cartoon acting with squash and stretch and secondary motion; stay on the same scene.",
        f"Style: {style.look}.",
        style.identity,
        style.accent,
        f"Camera: {camera}",
        style.forbid,
    ])
    negative = "text, letters, subtitles, logo, watermark, extra characters, colour other than the accent, scene change, morphing faces"
    return MotionPrompt(prompt=prompt, negative=negative, camera=camera)


# --------------------------------------------------------------------------- providers


@dataclass(frozen=True)
class ClipRequest:
    image_path: Path
    prompt: str
    negative_prompt: str
    duration_s: float
    aspect: str = ASPECT


@dataclass(frozen=True)
class ClipResult:
    video_path: Path
    usage: dict = field(default_factory=dict)      # provider-reported usage (seconds billed, job id, ...)
    actual_cost_usd: float | None = None           # None = not reported by the provider (unknown, not zero)


class ImageToVideoProvider(Protocol):
    name: str
    model: str
    usd_per_second: float | None                   # None = price unknown: no call is made

    def generate(self, request: ClipRequest, out_path: Path, timeout_s: float) -> ClipResult: ...


# transport(request, out_path, timeout_s) -> usage dict; it must write an mp4 at out_path
Transport = Callable[[ClipRequest, Path, float], dict]


def _ffmpeg_still_motion(request: ClipRequest, out_path: Path, timeout_s: float) -> dict:
    """Local, free stand-in: a slow zoom on the still (no network). Only for offline dry runs of the pipeline."""
    if shutil.which("ffmpeg") is None:
        raise KeyClipError("ffmpeg unavailable for the fake provider")
    fps, frames = 25, int(round(request.duration_s * 25))
    vf = (f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
          f"zoompan=z='min(zoom+0.0015,1.2)':d={frames}:s=540x960:fps={fps},format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(request.image_path),
                    "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", str(out_path)],
                   check=True, capture_output=True, timeout=timeout_s)
    return {"seconds": request.duration_s, "local": True}


class FakeProvider:
    """Offline provider for tests and dry runs. Free: actual cost 0.0 is a real measurement here."""

    name = "fake"
    model = "fake-i2v:v1"

    def __init__(self, transport: Transport | None = None, usd_per_second: float | None = 0.0, report_cost: bool = True):
        self._transport = transport or _ffmpeg_still_motion
        self.usd_per_second = usd_per_second
        self._report_cost = report_cost

    def generate(self, request: ClipRequest, out_path: Path, timeout_s: float) -> ClipResult:
        usage = dict(self._transport(request, out_path, timeout_s) or {})
        cost = usage.pop("cost_usd", 0.0) if self._report_cost else None
        return ClipResult(video_path=out_path, usage=usage, actual_cost_usd=cost)


class _StubProvider:
    """Placeholder for a real provider. The owner has not chosen it: no endpoint, key name or price is assumed."""

    name = "stub"
    model = "unconfigured"
    usd_per_second: float | None = None

    def __init__(self, transport: Transport | None = None, env: Mapping[str, str] | None = None):
        raise NotConfigured(
            f"key clip provider '{self.name}' is not configured: endpoint, credentials and price are an owner "
            "decision (docs/product/STORY_STUDIO_KEY_CLIPS_2026-10-28.md)")

    def generate(self, request: ClipRequest, out_path: Path, timeout_s: float) -> ClipResult:  # pragma: no cover
        raise NotConfigured(f"key clip provider '{self.name}' is not configured")


class VeoProvider(_StubProvider):
    name = "veo"


class SeedanceProvider(_StubProvider):
    name = "seedance"


class WanProvider(_StubProvider):
    name = "wan"


PROVIDERS: dict[str, type] = {"fake": FakeProvider, "veo": VeoProvider, "seedance": SeedanceProvider, "wan": WanProvider}


def provider_from_env(env: Mapping[str, str] | None = None, transport: Transport | None = None):
    """The provider named by STORY_KEY_CLIP_PROVIDER, or None when empty (feature disabled, the default).

    Raises UnknownProvider for an unknown name and NotConfigured for a stub; the caller then keeps the stills.
    """
    env = os.environ if env is None else env
    name = (env.get(ENV_PROVIDER) or "").strip().lower()
    if not name:
        return None
    cls = PROVIDERS.get(name)
    if cls is None:
        raise UnknownProvider(f"unknown key clip provider '{name}' (known: {', '.join(sorted(PROVIDERS))})")
    return cls(transport=transport)


# --------------------------------------------------------------------------- budget


@dataclass(frozen=True)
class KeyClipBudget:
    max_usd: float = DEFAULT_MAX_USD
    max_clips: int = DEFAULT_MAX_CLIPS
    max_total_s: float = DEFAULT_MAX_TOTAL_S
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_attempts: int = MAX_ATTEMPTS
    usd_per_second: float | None = None            # override of the provider rate (config), None = provider's own

    def __post_init__(self):
        object.__setattr__(self, "max_usd", min(max(float(self.max_usd), 0.0), ABSOLUTE_MAX_USD))
        object.__setattr__(self, "max_clips", min(max(int(self.max_clips), 0), MAX_CLIPS_LIMIT))
        object.__setattr__(self, "max_attempts", min(max(int(self.max_attempts), 1), MAX_ATTEMPTS))
        object.__setattr__(self, "timeout_s", max(float(self.timeout_s), 1.0))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "KeyClipBudget":
        env = os.environ if env is None else env

        def num(key, default, cast=float):
            try:
                value = cast(str(env.get(key, "")).strip())
            except (TypeError, ValueError):
                return default
            return value if math.isfinite(value) and value >= 0 else default

        rate = num(ENV_USD_PER_S, None)
        return cls(max_usd=num(ENV_MAX_USD, DEFAULT_MAX_USD), max_clips=num(ENV_MAX_CLIPS, DEFAULT_MAX_CLIPS, int),
                   timeout_s=num(ENV_TIMEOUT_S, DEFAULT_TIMEOUT_S), usd_per_second=rate)


# --------------------------------------------------------------------------- validation


def measure_clip(path: Path) -> dict:
    """ffprobe + ffmpeg blackdetect/freezedetect on a returned clip (IO)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=60).stdout
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        return {"has_video": False}

    def detect(vf):
        return subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", vf, "-an", "-f", "null", "-"],
                              capture_output=True, text=True, check=False, timeout=120).stderr

    return {
        "has_video": True,
        "duration_s": float(video.get("duration") or data["format"]["duration"]),
        "width": int(video["width"]), "height": int(video["height"]),
        "black": quality.parse_blackdetect(detect("blackdetect=d=0.15:pix_th=0.04")),
        "freeze": quality.parse_freezedetect(detect("freezedetect=n=-60dB:d=0.5")),
    }


def clip_problems(measurement: Mapping, requested_s: float, beat_s: float) -> list[str]:
    """Pure verdict on a measured clip; an empty list means the clip is usable."""
    if not measurement.get("has_video"):
        return ["no_video_stream"]
    problems = []
    duration = float(measurement.get("duration_s") or 0.0)
    needed = min(requested_s, beat_s)
    if duration < needed - DURATION_TOLERANCE_S:
        problems.append(f"too_short:{duration:.2f}s<{needed:.2f}s")
    if duration > 2 * requested_s + 1.0:
        problems.append(f"too_long:{duration:.2f}s")
    width, height = int(measurement.get("width") or 0), int(measurement.get("height") or 0)
    if width < MIN_WIDTH or height <= 0 or abs(width / height - ASPECT_RATIO) > ASPECT_TOLERANCE * ASPECT_RATIO:
        problems.append(f"bad_resolution:{width}x{height}")
    if duration > 0:
        black = sum(b - a for a, b in measurement.get("black", []))
        frozen = sum(b - a for a, b in measurement.get("freeze", []))
        if black / duration > MAX_BLACK_FRACTION:
            problems.append(f"black:{black:.2f}s")
        if frozen / duration > MAX_FROZEN_FRACTION:
            problems.append(f"frozen:{frozen:.2f}s")
    return problems


# --------------------------------------------------------------------------- orchestration


@dataclass
class Attempt:
    number: int
    estimated_usd: float
    actual_usd: float | None = None                # None = not reported (unknown)
    latency_s: float | None = None
    error: str | None = None
    problems: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


@dataclass
class ClipOutcome:
    beat_id: str
    status: str                                    # ok | failed | skipped_budget | skipped_invalid | rate_unknown | not_configured
    requested_s: float
    prompt: MotionPrompt | None = None
    clip_path: Path | None = None
    attempts: list[Attempt] = field(default_factory=list)


@dataclass
class KeyClipsReport:
    version: str
    provider: str | None
    model: str | None
    prompt_version: str
    budget_usd: float
    outcomes: list[ClipOutcome] = field(default_factory=list)

    @property
    def clips(self) -> dict[str, Path | None]:
        """beat id -> clip path, or None when the still must be kept. Beats not selected are absent."""
        return {o.beat_id: o.clip_path for o in self.outcomes}

    @property
    def estimated_usd(self) -> float:
        return round(sum(a.estimated_usd for o in self.outcomes for a in o.attempts), 6)

    @property
    def actual_usd(self) -> float | None:
        """Sum of reported costs, or None as soon as one attempt has no measurement (unknown is not zero)."""
        attempts = [a for o in self.outcomes for a in o.attempts]
        if any(a.actual_usd is None for a in attempts):
            return None
        return round(sum(a.actual_usd for a in attempts), 6)

    @property
    def actual_cost_complete(self) -> bool:
        return self.actual_usd is not None

    def to_dict(self) -> dict:
        return {
            "version": self.version, "provider": self.provider, "model": self.model, "prompt_version": self.prompt_version,
            "budget_usd": self.budget_usd, "estimated_usd": self.estimated_usd, "actual_usd": self.actual_usd,
            "actual_cost_complete": self.actual_cost_complete,
            "clips": [{
                "beat_id": o.beat_id, "status": o.status, "requested_s": o.requested_s,
                "clip_path": str(o.clip_path) if o.clip_path else None,
                "camera": o.prompt.camera if o.prompt else None,
                "attempts": [{"number": a.number, "estimated_usd": a.estimated_usd, "actual_usd": a.actual_usd,
                              "latency_s": a.latency_s, "error": a.error, "problems": a.problems} for a in o.attempts],
            } for o in self.outcomes],
        }


def _valid_image(path_str: str | None, image_root: Path | None) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str).resolve()
    if path.suffix.lower() not in _IMAGE_SUFFIXES or not path.is_file():
        return None
    if image_root is not None:
        try:
            path.relative_to(Path(image_root).resolve())
        except ValueError:
            return None
    return path


def _call_with_timeout(fn, timeout_s: float):
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fn).result(timeout=timeout_s)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def make_key_clips(
    beats: Sequence,
    provider,
    budget: KeyClipBudget | None = None,
    *,
    out_dir: Path,
    style: Style = STYLE_1930S_RUBBER_HOSE,
    image_root: Path | None = None,
    measure: Callable[[Path], dict] = measure_clip,
    clock: Callable[[], float] = time.monotonic,
) -> KeyClipsReport:
    """Generate clips for the selected key beats; never raises for a single beat's failure.

    `provider=None` (feature disabled) returns an empty report. Each selected beat ends with a clip path or None.
    """
    budget = budget or KeyClipBudget()
    report = KeyClipsReport(version=KEY_CLIPS_VERSION, provider=getattr(provider, "name", None),
                            model=getattr(provider, "model", None), prompt_version=MOTION_PROMPT_VERSION,
                            budget_usd=budget.max_usd)
    if provider is None or budget.max_clips == 0:
        return report
    selected = select_key_beats(beats, budget.max_clips, budget.max_total_s)
    rate = budget.usd_per_second if budget.usd_per_second is not None else getattr(provider, "usd_per_second", None)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    committed = 0.0
    stop_status: str | None = None

    for beat in selected:
        requested = clip_seconds(beat)
        outcome = ClipOutcome(beat_id=beat.id, status="failed", requested_s=requested)
        report.outcomes.append(outcome)
        if stop_status:
            outcome.status = stop_status
            continue
        if rate is None:
            outcome.status = stop_status = "rate_unknown"   # the cap cannot be enforced without a price
            continue
        image = _valid_image(beat.image_path, image_root)
        if image is None:
            outcome.status = "skipped_invalid"
            continue
        outcome.prompt = build_motion_prompt(beat, style)
        request = ClipRequest(image_path=image, prompt=outcome.prompt.prompt, negative_prompt=outcome.prompt.negative,
                              duration_s=requested)
        estimate = round(requested * float(rate), 6)

        for number in range(1, budget.max_attempts + 1):
            if committed + estimate > budget.max_usd + 1e-9:
                outcome.status = "skipped_budget" if not outcome.attempts else "failed"
                break
            attempt = Attempt(number=number, estimated_usd=estimate)
            outcome.attempts.append(attempt)
            out_path = out_dir / f"{beat.id}.a{number}.mp4"
            started = clock()
            try:
                result = _call_with_timeout(lambda: provider.generate(request, out_path, budget.timeout_s), budget.timeout_s)
                attempt.usage = dict(result.usage)
                attempt.actual_usd = result.actual_cost_usd if isinstance(result.actual_cost_usd, (int, float)) else None
                if Path(result.video_path).resolve() != out_path.resolve() or not out_path.is_file():
                    raise KeyClipError("provider did not write the expected file")
                attempt.problems = clip_problems(measure(out_path), requested, beat.duration_s)
                if attempt.problems:
                    raise KeyClipError("clip rejected by validation")
            except NotConfigured as exc:
                attempt.error = f"NotConfigured: {exc}"
                outcome.status = stop_status = "not_configured"
            except concurrent.futures.TimeoutError:
                attempt.error = f"timeout after {budget.timeout_s:.0f}s"
            except Exception as exc:  # provider/IO/ffprobe: recorded, the still is kept
                attempt.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            else:
                outcome.status, outcome.clip_path = "ok", out_path
            finally:
                attempt.latency_s = round(clock() - started, 3)
                # a failed or timed-out call may still be billed: count the estimate when nothing was reported
                committed += attempt.actual_usd if attempt.actual_usd is not None else attempt.estimated_usd
            if outcome.status in ("ok", "not_configured"):
                break
            out_path.unlink(missing_ok=True)
    return report
