"""Sous-titres Faceloop du récit illustré : les mots chronométrés de la voix, posés sur la timeline, par `engine.captions`.

Aucun style maison : `captions.build_cues` / `write_ass` / `write_srt` (zone de sécurité 12-72 %), style du script
(`caption_style`, défaut `bold_stroke`, `off` = aucune incrustation).
"""
from __future__ import annotations

from pathlib import Path

from .. import captions

RESOLUTION = "1080x1920"


def _clean(words) -> list[dict]:
    return [{"text": w["text"], "start": float(w["start"]), "end": float(w["end"])} for w in (words or [])
            if isinstance(w, dict) and isinstance(w.get("text"), str) and w["text"].strip()
            and isinstance(w.get("start"), (int, float)) and isinstance(w.get("end"), (int, float))]


def build_cues(timeline: dict, voices: dict) -> list[dict]:
    """Les mots de chaque scène (secondes relatives à sa narration) sont décalés de son `audio_start` : `captions.build_cues` cumule
    les durées de bloc, donc un bloc d'attente initial puis, par scène, l'intervalle jusqu'au `audio_start` suivant (ou la fin)."""
    slots = timeline["scenes"]
    blocks = [([], slots[0]["audio_start"])]
    for i, slot in enumerate(slots):
        end = slots[i + 1]["audio_start"] if i + 1 < len(slots) else timeline["total_s"]
        blocks.append((_clean(voices[slot["id"]].get("words")), end - slot["audio_start"]))
    return captions.build_cues(blocks)


def write(cues: list[dict], folder: Path, story_id: str, style: str) -> Path | None:
    """Écrit le .srt Faceloop (toujours) et `captions.ass` ; renvoie le .ass à incruster, ou None si le style est `off`."""
    captions.write_srt(cues, str(folder / f"{story_id}.srt"))
    if style == captions.CAPTIONS_OFF:
        return None
    return Path(captions.write_ass(cues, str(folder / "captions.ass"), style, RESOLUTION))


def issues(cues: list[dict], ass: Path | None, style: str, total_s: float) -> list[str]:
    """Contrôles d'après-calage (relus par un humain, pas bloquants) : .ass avec au moins un événement, au moins un cue, aucun cue hors durée."""
    out = []
    if style != captions.CAPTIONS_OFF:
        if ass is None or not ass.is_file() or "Dialogue:" not in ass.read_text(encoding="utf-8"):
            out.append("captions: the .ass file is missing or has no event")
        if not cues:
            out.append("captions: no cue (the voice returned no timed words)")
    late = [c["index"] for c in cues if c["start"] < 0 or c["end"] > total_s + 0.05]
    if late:
        out.append(f"captions: cue(s) {late[:5]} outside the video duration")
    return out
