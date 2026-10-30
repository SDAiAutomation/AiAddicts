"""Calage voix d'abord : les durées de scène viennent de l'audio MESURÉ, jamais l'inverse (la parole n'est jamais coupée).

Pur. Les durées audio sont fournies par l'appelant (ffprobe sur les fichiers réels, ou durées de mots ElevenLabs).
"""
from __future__ import annotations

import math

WORDS_PER_SECOND = {"fr": 2.7, "en": 2.5}  # estimation AVANT synthèse, remplacée par la mesure ensuite
PAUSE_S = 0.35            # silence entre deux narrations : aucune superposition
MIN_SCENE_S = 2.5
READ_S_PER_WORD = 0.32    # temps de lecture du texte à l'écran
FINAL_HOLD_S = 3.0        # le dernier plan laisse le temps de retenir la leçon
HOOK_LEAD_S = 0.15        # départ quasi immédiat : l'accroche ne commence pas dans le silence


def estimate_audio_seconds(text: str, language: str) -> float:
    words = max(1, len(text.split()))
    return round(words / WORDS_PER_SECOND.get(language, 2.5), 2)


def schedule(plan: dict, audio_seconds: dict[str, float], *, pause_s: float = PAUSE_S) -> dict:
    """Timeline `{scenes:[{id,start,end,audio_start,audio_end,transition,...}], total_s, ...}`.

    Chaque scène dure : lead + audio + pause (+ prolongation pour lire le texte, + maintien final). L'audio d'une
    scène commence APRÈS la fin de la précédente (jamais de recouvrement). Les transitions chevauchent la PAUSE
    de fin de scène, donc jamais la parole."""
    scenes = plan["scenes"]
    ids = [s["id"] for s in scenes]
    if set(audio_seconds) != set(ids):
        raise ValueError("measured audio durations must cover exactly the scene ids")
    for sid, value in audio_seconds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"invalid audio duration for {sid}")
    cursor, out = 0.0, []
    last = len(scenes) - 1
    for i, scene in enumerate(scenes):
        audio = float(audio_seconds[scene["id"]])
        lead = HOOK_LEAD_S if i == 0 else 0.1
        read = len(scene.get("on_screen_text", "").split()) * READ_S_PER_WORD + 0.6 if scene.get("on_screen_text") else 0.0
        tail = FINAL_HOLD_S if i == last else pause_s
        duration = max(MIN_SCENE_S, lead + audio + tail, read)
        out.append({
            "id": scene["id"], "start": round(cursor, 3), "end": round(cursor + duration, 3), "duration": round(duration, 3),
            "audio_start": round(cursor + lead, 3), "audio_end": round(cursor + lead + audio, 3),
            "transition": scene["transition"], "camera": scene.get("camera", "still"),
        })
        cursor += duration
    target = plan["target_duration_s"]
    return {"scenes": out, "total_s": round(cursor, 3), "target_s": target, "delta_s": round(cursor - target, 3),
            "within_10_percent": abs(cursor - target) <= 0.1 * target}


def check_no_overlap(timeline: dict) -> list[str]:
    errors, previous_end = [], 0.0
    for scene in timeline["scenes"]:
        if scene["audio_start"] < previous_end - 1e-6:
            errors.append(f"{scene['id']}: narration starts before the previous one ends")
        if not scene["start"] <= scene["audio_start"] < scene["audio_end"] <= scene["end"] + 1e-6:
            errors.append(f"{scene['id']}: narration is outside its scene")
        previous_end = scene["audio_end"]
    return errors


def srt(plan: dict, timeline: dict) -> str:
    """Sous-titres optionnels : une entrée par scène (texte de narration), bornes = bornes de la parole."""
    def stamp(t: float) -> str:
        ms = round(t * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    rows = []
    for n, (scene, slot) in enumerate(zip(plan["scenes"], timeline["scenes"]), start=1):
        rows.append(f"{n}\n{stamp(slot['audio_start'])} --> {stamp(slot['audio_end'])}\n{scene['narration'].strip()}\n")
    return "\n".join(rows)
