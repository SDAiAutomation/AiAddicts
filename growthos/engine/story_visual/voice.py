"""Voix off par scène : fournisseur injectable, cache par locataire, reprise, budget fail-closed.

`elevenlabs_provider()` enveloppe `engine.tts.synthesize_with_timestamps` (PAYANT, clé serveur, retry existant). Les tests et
le mode hors ligne utilisent `SimulatedVoiceProvider` (ffmpeg, aucun réseau). La durée de chaque scène sera MESURÉE sur
l'audio produit (`render.audio_duration`) puis passée à `timing.schedule` : la voix décide du temps.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import asset_store, tts
from . import cache as cache_mod
from . import cost, render, schema, store, timing

_SAFE = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass
class VoiceResult:
    path: str | None
    words: list | None = None
    cost_usd: float | None = None
    error: str | None = None


VoiceProvider = Callable[..., VoiceResult]


def voice_rate_per_1k(env=None) -> float | None:
    env = os.environ if env is None else env
    try:
        rate = float(env.get("ELEVENLABS_USD_PER_1K_CHARS", "").strip())
    except ValueError:
        return None
    return rate if rate >= 0 else None


def elevenlabs_provider(env=None) -> VoiceProvider:
    """Adaptateur vers la synthèse existante. Un échec devient `VoiceResult(error=...)`, jamais une exception brute."""
    def call(text: str, voice_id: str, out_path: str) -> VoiceResult:
        try:
            words = tts.synthesize_with_timestamps(text, voice_id, out_path)
        except RuntimeError as exc:
            return VoiceResult(None, None, None, f"voice_error: {str(exc)[:120]}")
        rate = voice_rate_per_1k(env)
        return VoiceResult(out_path, words, None if rate is None else len(text) / 1000 * rate)
    return call


class SimulatedVoiceProvider:
    """Voix de substitution : sinusoïde basse (aucun réseau, aucun coût), durée = estimation de parole ; mots répartis."""

    def __init__(self, language: str = "fr"):
        self.language = language
        self.calls: list[str] = []
        self.fail_next = 0

    def __call__(self, text: str, voice_id: str, out_path: str) -> VoiceResult:
        self.calls.append(text)
        if self.fail_next > 0:
            self.fail_next -= 1
            return VoiceResult(None, None, None, "voice_error: simulated")
        seconds = timing.estimate_audio_seconds(text, self.language)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency=180:sample_rate=48000:duration={seconds:.3f}", "-af", "volume=0.05",
                        "-c:a", "libmp3lame", str(out_path)], check=True, capture_output=True)
        names = text.split()
        step = seconds / max(1, len(names))
        words = [{"text": w, "start": round(i * step, 3), "end": round((i + 1) * step, 3)} for i, w in enumerate(names)]
        return VoiceResult(out_path, words, 0.0)


def voice_key(tenant_id: str, text: str, voice_id: str) -> str:
    return asset_store.make_key(kind="story_visual_voice", tenant=tenant_id, text=text.strip(), voice=voice_id,
                                model=tts.TTS_MODEL_ID, settings=tts.TTS_VOICE_SETTINGS)


MAX_ATTEMPTS_PER_SCENE = 3
MAX_AUDIO_SECONDS = 60.0  # une narration de scène (≤ 420 caractères) ne dure jamais une minute : au-delà, fichier refusé


def synthesize_story(plan: dict, *, tenant_id: str, work_dir: str | Path, provider: VoiceProvider,
                     tracker: cost.BudgetTracker, voice_id: str | None, rate_per_1k: float | None,
                     disk_cache: cache_mod.DiskImageCache | None = None) -> dict:
    """`{scene_id: {status, path, duration_s, words, cost_usd, cost_kind, cache_hit, error, attempts}}`. Plan revalidé (fail-closed),
    exécution verrouillée, manifeste atomique, dépense déjà faite reprise dans `tracker`, échec par scène reprenable puis
    `needs_review`. Lève `BudgetExceeded` AVANT l'appel si le coût est inconnu (rate None) ou dépasserait le plafond."""
    errors = schema.validate_story_plan(plan)
    if errors:
        raise ValueError("invalid plan: " + "; ".join(errors[:3]))
    voice_id = voice_id or plan.get("voice_id")
    if not voice_id or not re.fullmatch(r"[A-Za-z0-9]{8,64}", str(voice_id)):
        raise ValueError("no valid voice configured for this story")
    if not _SAFE.fullmatch(tenant_id):
        raise ValueError("invalid tenant or story id")
    folder = Path(work_dir).resolve() / tenant_id / plan["story_id"]
    folder.mkdir(parents=True, exist_ok=True)
    with store.job_lock(folder):
        return _synthesize(plan, folder, tenant_id, provider, tracker, voice_id, rate_per_1k, disk_cache)


def _synthesize(plan, folder, tenant_id, provider, tracker, voice_id, rate_per_1k, disk_cache) -> dict:
    manifest_path = folder / "voice.json"
    manifest = store.load_manifest(manifest_path)
    for sid, entry in manifest.items():
        if isinstance(entry, dict) and entry.get("status") == "done":
            tracker.seed(f"voice:{sid}", entry.get("cost_usd"), entry.get("cost_kind", cost.MEASURED))
    for scene in plan["scenes"]:
        sid, text = scene["id"], scene["narration"].strip()
        key = voice_key(tenant_id, text, voice_id)
        out = folder / f"voice-{sid}.mp3"
        previous = manifest.get(sid) or {}
        attempts = previous.get("attempts", 0) if previous.get("key") == key else 0
        if previous.get("status") == "done" and previous.get("key") == key and out.is_file():
            continue
        if previous.get("status") == "needs_review" and previous.get("key") == key:
            continue
        words_path = folder / f"voice-{sid}.words.json"
        if disk_cache and disk_cache.restore(key, out) and _restore_words(disk_cache, key, words_path):
            tracker.seed(f"voice:{sid}", 0.0, cost.CACHED)
            words = json.loads(words_path.read_text(encoding="utf-8"))
            manifest[sid] = _done(out, key, render.audio_duration(out), words, 0.0, cost.CACHED, True, attempts)
        else:
            item = f"voice:{sid}"
            tracker.reserve(item, None if rate_per_1k is None else len(text) / 1000 * rate_per_1k)
            attempts += 1
            try:
                result = provider(text, voice_id, str(out))
            except Exception as exc:  # noqa: BLE001 - peut avoir été facturé : coût inconnu
                tracker.record(item, None)
                result = VoiceResult(None, None, None, f"provider_exception:{type(exc).__name__}")
            else:
                reason = None
                if result.path and Path(result.path).resolve() != out.resolve():
                    reason = "unexpected_output_path"
                elif result.path and Path(result.path).is_file():
                    try:
                        duration = render.audio_duration(out)
                        if not 0.2 <= duration <= MAX_AUDIO_SECONDS:
                            reason = "invalid_audio_duration"
                    except render.RenderError:
                        reason = "unreadable_audio"
                elif result.path:
                    reason = "missing_output"
                if result.path and reason is None:
                    kind = cost.MEASURED if result.cost_usd is not None else cost.UNPRICED
                    tracker.record(item, result.cost_usd, kind)
                    if disk_cache:
                        words_path.write_text(json.dumps(result.words or []), encoding="utf-8")
                        disk_cache.save(key, out)
                        _save_words(disk_cache, key, words_path)
                    manifest[sid] = _done(out, key, duration, result.words, result.cost_usd, kind, False, attempts)
                    store.save_manifest(manifest_path, manifest)
                    continue
                tracker.record(item, None)
                result = VoiceResult(None, None, None, reason or result.error or "unknown")
            manifest[sid] = {"status": "needs_review" if attempts >= MAX_ATTEMPTS_PER_SCENE else "failed", "key": key,
                             "error": result.error or "unknown", "cost_usd": None, "cost_kind": cost.UNPRICED,
                             "cache_hit": False, "attempts": attempts}
        store.save_manifest(manifest_path, manifest)
    return manifest


def _done(path, key, duration, words, usd, kind, hit, attempts=1) -> dict:
    return {"status": "done", "path": str(path), "key": key, "duration_s": duration, "words": words or [],
            "cost_usd": usd, "cost_kind": kind, "cache_hit": hit, "error": None, "attempts": attempts}


def _words_cache(disk_cache: cache_mod.DiskImageCache) -> cache_mod.DiskImageCache:
    return cache_mod.DiskImageCache(disk_cache.dir.parent, disk_cache.dir.name, ".json")


def _save_words(disk_cache, key, words_path) -> None:
    _words_cache(disk_cache).save(key, words_path)


def _restore_words(disk_cache, key, dest) -> bool:
    return _words_cache(disk_cache).restore(key, dest)


def measured_durations(manifest: dict) -> dict[str, float]:
    """Durées audio MESURÉES, prêtes pour `timing.schedule` ; lève si une scène n'a pas d'audio."""
    missing = [sid for sid, m in manifest.items() if m.get("status") != "done"]
    if missing:
        raise ValueError("voice missing for scenes: " + ", ".join(missing))
    return {sid: m["duration_s"] for sid, m in manifest.items()}
