"""Sous-titres Faceloop du récit illustré : les mots chronométrés de la voix, posés sur la timeline, par `engine.captions`.

Aucun style maison : `captions.build_cues` / `write_ass` / `write_srt` (zone de sécurité 12-72 %), style du script
(`caption_style`, défaut `bold_stroke`, `off` = aucune incrustation).
"""
from __future__ import annotations

import os
from pathlib import Path

from .. import captions, quiz_motion

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


def brand_font() -> tuple[str | None, Path | None]:
    """(police, dossier de polices) comme le Standard (assembler.py) : Poppins livrée dans assets/fonts, sauf SUBTITLE_FONT ou fichiers absents."""
    if os.environ.get("SUBTITLE_FONT") or not quiz_motion.brand_font_available():
        return None, None
    return quiz_motion.BRAND_FONT, quiz_motion.FONT_DIR


def write(cues: list[dict], folder: Path, story_id: str, style: str, font: str | None = None) -> Path | None:
    """Écrit le .srt Faceloop (toujours) et `captions.ass` ; renvoie le .ass à incruster, ou None si le style est `off`."""
    captions.write_srt(cues, str(folder / f"{story_id}.srt"))
    if style == captions.CAPTIONS_OFF:
        return None
    return Path(captions.write_ass(cues, str(folder / "captions.ass"), style, RESOLUTION, font=font))


def issues(cues: list[dict], ass: Path | None, style: str, total_s: float, timeline: dict | None = None) -> list[str]:
    """Contrôles d'après-calage (relus par un humain, pas bloquants) : .ass avec au moins un événement, au moins un cue, aucun cue hors durée,
    mots calés à l'envers, mots qui débordent de leur bloc de scène (avec `timeline`) et cues qui se chevauchent."""
    out = []
    if style != captions.CAPTIONS_OFF:
        if ass is None or not ass.is_file() or "Dialogue:" not in ass.read_text(encoding="utf-8"):
            out.append("captions: the .ass file is missing or has no event")
        if not cues:
            out.append("captions: no cue (the voice returned no timed words)")
    late = [c["index"] for c in cues if c["start"] < 0 or c["end"] > total_s + 0.05]
    if late:
        out.append(f"captions: cue(s) {late[:5]} outside the video duration")
    words = [w for c in cues for w in c.get("words", [])]
    if any(w["end"] < w["start"] for w in words):
        out.append("captions: a word ends before it starts")
    if timeline:
        starts = [s["audio_start"] for s in timeline["scenes"]]
        ends = starts[1:] + [timeline["total_s"]]
        for w in words:
            blocks = [e for a, e in zip(starts, ends) if a - 1e-6 <= w["start"] < e - 1e-6]  # tolérance : audio_start est arrondi à 3 décimales
            if blocks and w["end"] > blocks[0] + 0.05:
                out.append("captions: a word overflows its scene block")
                break
    if any(b["start"] < a["end"] - 0.01 for a, b in zip(cues, cues[1:])):
        out.append("captions: overlapping cues")
    return out
