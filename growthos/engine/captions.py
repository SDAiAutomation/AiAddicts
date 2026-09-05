"""Build an SRT caption file from per-word timing.

Sous-titres animés : au lieu d'un bloc entier affiché d'un coup pendant
toute sa durée, chaque cue ne montre que quelques mots, enchaînés au débit
réel de la voix (timing ElevenLabs, voir engine/tts.synthesize_with_timestamps)
— look "CapCut/Reels" standard plutôt qu'un pavé de texte statique.
"""
from pathlib import Path

# 2-4 mots par écran (choisi avec l'utilisateur) : assez court pour bouger
# vite, assez long pour rester lisible.
_WORDS_PER_CUE = 3


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_cues(block_words: list[tuple[list[dict], float]], gap: float = 0.15) -> list[dict]:
    """`block_words` : une entrée par bloc, dans l'ordre de lecture —
    (mots du bloc [{"text","start","end"} relatifs au bloc], durée réelle
    du bloc en secondes, mesurée par ffprobe). La durée réelle (pas juste
    la fin du dernier mot) sert à décaler les blocs suivants, pour rester
    calé sur l'audio concaténé (video.concat_audio ne met aucun blanc entre
    blocs — un décalage ici dériverait de bloc en bloc).

    Regroupe les mots de chaque bloc par paquets de `_WORDS_PER_CUE`.

    Construit d'abord les bornes brutes de chaque groupe, puis leur applique
    la marge `gap` en une deuxième passe, bornée par le début du groupe
    *suivant* (bloc suivant compris) — sinon la marge d'un groupe peut
    déborder sur le début du suivant quand les mots s'enchaînent vite,
    produisant des cues qui se chevauchent dans le SRT."""
    raw: list[list] = []  # [start, end, text], sans la marge
    cursor = 0.0
    for words, block_duration in block_words:
        for start in range(0, len(words), _WORDS_PER_CUE):
            chunk = words[start:start + _WORDS_PER_CUE]
            text = " ".join(w["text"] for w in chunk)
            raw.append([cursor + chunk[0]["start"], cursor + chunk[-1]["end"], text])
        cursor += block_duration
    total_duration = cursor

    cues = []
    for i, (start, end, text) in enumerate(raw):
        next_start = raw[i + 1][0] if i + 1 < len(raw) else total_duration
        cue_end = min(end + gap, next_start)
        cues.append({"index": i + 1, "start": start, "end": max(cue_end, start + 0.1), "text": text})
    return cues


def write_srt(cues: list[dict], out_path: str) -> str:
    lines = []
    for cue in cues:
        lines.append(str(cue["index"]))
        lines.append(f"{format_timestamp(cue['start'])} --> {format_timestamp(cue['end'])}")
        lines.append(cue["text"])
        lines.append("")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
