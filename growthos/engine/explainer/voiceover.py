"""Voix off de l'Explainer : une synthèse ElevenLabs par ligne de narration, puis placement selon la parole réelle.

Réutilise `engine/tts.py` (même modèle, mêmes réglages, mêmes reprises sur 429/5xx que le reste du moteur) et
`engine/voices.py` (même résolution de voix). La clé ElevenLabs vient de l'environnement (`.env` chargé par
`python-dotenv`) : elle n'est jamais lue ici, affichée ni écrite dans un fichier.

    python -m engine.explainer.voiceover timeline.js out_dir [--voice VOICE_ID]

Sortie : `out_dir/voice.wav` (toutes les lignes mixées à leur place) et `out_dir/voiceover.report.json` (durées,
dépassements, mots avec leur instant absolu, coût estimé). Une ligne déjà synthétisée avec le même texte et la même
voix est réutilisée depuis le disque (pas de nouvelle facturation).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from engine import tts, voices

MAX_TEMPO = 1.15      # accélération maximale tolérée pour faire tenir une ligne dans sa fenêtre
MIN_GAP = 0.15        # silence à garder avant la ligne suivante (s)
SENTENCE_GAP = 0.38   # respiration naturelle après une phrase, mesurée depuis le dernier mot prononcé
QUESTION_GAP = 0.48   # une question laisse un peu plus de place à l'idée
SHORT_GAP = 0.28      # fragment qui se poursuit à la ligne suivante
TAIL = 1.2            # fin de vidéo après la dernière parole


def _line_key(text: str, voice_id: str) -> str:
    raw = json.dumps([text, voice_id, tts.TTS_MODEL_ID, tts.TTS_VOICE_SETTINGS], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def synthesize_lines(narration: list, out_dir: Path, voice_id: str, api_key: str | None = None) -> list[dict]:
    """Synthétise (ou relit sur disque) chaque ligne. Renvoie une entrée par ligne : start, text, path, words, duration."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for index, (start, text) in enumerate(narration):
        key = _line_key(text, voice_id)
        audio, words_path = out_dir / f"line-{index:02d}-{key}.mp3", out_dir / f"line-{index:02d}-{key}.words.json"
        cached = audio.exists() and audio.stat().st_size > 0 and words_path.exists()
        if cached:
            words = json.loads(words_path.read_text(encoding="utf-8"))
        else:
            words = tts.synthesize_with_timestamps(text, voice_id, str(audio), api_key)
            words_path.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        lines.append({"index": index, "start": float(start), "text": text, "path": str(audio), "words": words,
                      "duration": tts.get_duration_seconds(str(audio)), "chars": 0 if cached else len(text), "cached": cached})
    return lines


def plan_tempo(lines: list[dict], total: float) -> None:
    """Ajoute `tempo` (1.0 = inchangé) et `overflow` (s, >0 = la ligne déborde sur la suivante malgré le tempo)."""
    for i, line in enumerate(lines):
        window = (lines[i + 1]["start"] if i + 1 < len(lines) else total) - line["start"] - MIN_GAP
        tempo = 1.0 if line["duration"] <= window else min(MAX_TEMPO, line["duration"] / max(window, 0.1))
        line["tempo"] = round(tempo, 3)
        line["overflow"] = round(max(0.0, line["duration"] / tempo - window), 2)


def pace_lines(lines: list[dict], lead_in: float = 0.4) -> float:
    """Place les lignes à partir de leurs vrais mots, puis renvoie la durée du mix.

    L'estimation caractères/seconde sert au premier storyboard seulement. Elle
    ne doit pas créer des secondes de silence une fois la voix synthétisée.
    La fin muette d'un MP3 peut se superposer au début de la ligne suivante ;
    seuls les mots prononcés déterminent l'espace audible entre deux phrases.
    """
    if not lines:
        return round(max(0.0, lead_in) + TAIL, 2)
    cursor = max(0.0, lead_in)
    for line in lines:
        line["start"] = round(cursor, 3)
        line["tempo"] = 1.0
        line["overflow"] = 0.0
        word_end = max((float(w["end"]) for w in line["words"]), default=float(line["duration"]))
        speech_end = min(float(line["duration"]), word_end) if word_end > 0 else float(line["duration"])
        text = line["text"].rstrip()
        pause = QUESTION_GAP if text.endswith(("?", "!")) else SENTENCE_GAP if text.endswith((".", "…")) else SHORT_GAP
        cursor = line["start"] + speech_end + pause
    last = lines[-1]
    return round(max(last["start"] + last["duration"], cursor - pause) + TAIL, 2)


def mix_lines(lines: list[dict], total: float, out_path: Path) -> Path:
    """Pose chaque ligne à son instant (adelay) et mixe le tout dans un WAV stéréo 48 kHz de `total` secondes."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for line in lines:
        cmd += ["-i", line["path"]]
    parts = []
    for i, line in enumerate(lines):
        delay = int(round(line["start"] * 1000))
        tempo = f"atempo={line['tempo']}," if line["tempo"] != 1.0 else ""
        parts.append(f"[{i}:a]{tempo}aresample=48000,aformat=channel_layouts=stereo,adelay={delay}|{delay}[a{i}]")
    inputs = "".join(f"[a{i}]" for i in range(len(lines)))
    parts.append(f"{inputs}amix=inputs={len(lines)}:normalize=0,apad=whole_dur={total},atrim=0:{total}[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", "-ac", "2", str(out_path)]
    subprocess.run(cmd, check=True)
    return out_path


def build_voiceover(narration: list, total: float, out_dir: str | Path, voice_id: str | None = None, api_key: str | None = None) -> dict:
    out_dir = Path(out_dir)
    voice = voice_id or voices.resolve_voice({})
    lines = synthesize_lines(narration, out_dir, voice, api_key)
    total = pace_lines(lines, narration[0][0] if narration else 0.4)
    wav = mix_lines(lines, total, out_dir / "voice.wav")
    billed = sum(line["chars"] for line in lines)
    rate = os.environ.get("ELEVENLABS_USD_PER_1K_CHARS", "").strip()
    report = {
        "voiceId": voice, "model": tts.TTS_MODEL_ID, "wav": str(wav), "durationSeconds": total,
        "charsBilledThisRun": billed, "costUsdThisRun": round(billed / 1000 * float(rate), 4) if rate else None,  # None = tarif inconnu
        "lines": [{k: line[k] for k in ("index", "start", "text", "duration", "tempo", "overflow", "cached")}
                  | {"end": round(line["start"] + line["duration"] / line["tempo"], 2)} for line in lines],
        "words": [{"text": w["text"], "start": round(line["start"] + w["start"] / line["tempo"], 3),
                   "end": round(line["start"] + w["end"] / line["tempo"], 3)} for line in lines for w in line["words"]],
    }
    (out_dir / "voiceover.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    from .render import read_video_async

    load_dotenv()
    voice = argv[argv.index("--voice") + 1] if "--voice" in argv else None
    if len(argv) < 2:
        print(__doc__)
        return 2
    video = asyncio.run(read_video_async(argv[0]))
    report = build_voiceover(video["narration"], video["duration"], argv[1], voice)
    for line in report["lines"]:
        flag = "  <-- DEBORDE" if line["overflow"] > 0 else ""
        print(f"{line['start']:5.1f}s  {line['duration']:4.1f}s  x{line['tempo']:<5}{flag}  {line['text'][:60]}")
    print(f"caracteres factures : {report['charsBilledThisRun']}  cout : {report['costUsdThisRun']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
