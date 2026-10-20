"""Worker job: render the vertical exports of one chapter of a rendered five-level quiz.

Runs on an ephemeral worker, so nothing from the master render is assumed to exist on disk: the narration of every
block is restored from the asset cache (same key as the master render, see assembler.voice_text_for) and the
countdown-padded audio is rebuilt with the shared helper. The cache is best-effort and is NOT always complete (a real
50-question run kept 100 of 107 voices and 95 of 100 word timings), so a miss is repaired instead of failing:
audio without timings gets evenly spread timings, and a block with no cached voice is synthesized again (bounded
number of blocks and characters) and cached. The re-synthesized narration can differ slightly in intonation from the
master, which is acceptable because each export is a self-consistent video measured from its own audio.

Isolation: one private temp directory per job (random name), removed on exit; storage paths are derived from the
content item id and the exported version only; the browser never receives storage paths (the site signs access
after reading the row under RLS).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from . import asset_store, assembler, quiz_shorts, script as script_module, storage, tts

STORAGE_PREFIX = "shorts"


def export_storage_path(content_item_id: str, version: int | None, file_name: str) -> str:
    """`<item>/shorts/v<n>/<file>` ; the file name is one of the fixed whitelisted names (never user text)."""
    allowed = {f"{stem}{suffix}.mp4" for stem in quiz_shorts.CHAPTER_STEMS.values()
               for suffix in ("", *(f"_part{n}" for n in range(1, 11)))}
    if file_name not in allowed:
        raise ValueError("nom de fichier d'export inattendu")
    return f"{content_item_id}/{STORAGE_PREFIX}/v{version or 0}/{file_name}"


MAX_RESYNTH_BLOCKS = 20
MAX_RESYNTH_CHARS = 6000


def approximate_words(text: str, duration: float) -> list[dict]:
    """Word timings spread evenly over the narration, for blocks whose real timings were not cached."""
    words = text.split()
    step = duration / max(1, len(words))
    return [{"text": w, "start": round(i * step, 3), "end": round(max(i * step, (i + 1) * step - 0.02), 3)} for i, w in enumerate(words)]


def restore_audio(data: dict, work_dir: Path) -> dict:
    """Rebuild `work_dir/audio` for every block. Returns counters {restored, approximate_words, synthesized}."""
    voice_id = data.get("voice_id")
    if not voice_id:
        raise quiz_shorts.ExportError("Voix du master inconnue : régénère la vidéo complète.")
    (work_dir / "audio").mkdir(parents=True, exist_ok=True)
    stats = {"restored": 0, "approximate_words": 0, "synthesized": 0}
    missing = []
    for index, block in enumerate(data["blocks"], 1):
        raw = work_dir / "audio" / f"block-{index:02d}.mp3"
        words = work_dir / "audio" / f"block-{index:02d}.words.json"
        voice_text = assembler.voice_text_for(data, block)
        key = asset_store.make_key(kind="voice", text=voice_text, voice_id=voice_id,
                                   model=tts.TTS_MODEL_ID, settings=tts.TTS_VOICE_SETTINGS)
        if asset_store.restore_voice(key, raw, words):
            stats["restored"] += 1
        elif asset_store.restore_voice_audio(key, raw):
            words.write_text(json.dumps(approximate_words(block["text"], tts.get_duration_seconds(str(raw))), ensure_ascii=False), encoding="utf-8")
            stats["approximate_words"] += 1
        else:
            missing.append((raw, words, key, voice_text))
    if missing:
        if len(missing) > MAX_RESYNTH_BLOCKS or sum(len(m[3]) for m in missing) > MAX_RESYNTH_CHARS:
            raise quiz_shorts.ExportError(f"{len(missing)} voix manquent dans le cache : régénère la vidéo complète.")
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise quiz_shorts.ExportError("Voix du master introuvables dans le cache et synthèse indisponible : régénère la vidéo complète.")
        for raw, words, key, voice_text in missing:
            timings = tts.synthesize_with_timestamps(voice_text, voice_id, str(raw), api_key)
            words.write_text(json.dumps(timings, ensure_ascii=False), encoding="utf-8")
            asset_store.save_voice(key, raw, words, None)  # cached: the next export (and a re-render) reuse this very voice
            stats["synthesized"] += 1
    for index, block in enumerate(data["blocks"], 1):
        if float(block.get("hold_after_seconds") or 0) > 0:
            raw = work_dir / "audio" / f"block-{index:02d}.mp3"
            quiz_shorts.ensure_padded_audio(block, raw, quiz_shorts.audio_path(work_dir, index, block))
    return stats


def process(client, row: dict) -> dict:
    """Render and upload the outputs of one claimed export row. Returns the fields to store on success."""
    content_item_id, chapter = row["content_item_id"], int(row["chapter"])
    item = (client.table("content_items").select("script, current_version_id")
            .eq("id", content_item_id).single().execute().data)
    if item.get("current_version_id") != row.get("source_version_id"):
        raise quiz_shorts.ExportError("La vidéo a été régénérée depuis la demande : relance l'export.")
    data = script_module.normalize_script(item["script"])
    script_module.validate_script(data)
    version = None
    if row.get("source_version_id"):
        found = (client.table("content_versions").select("version_number").eq("id", row["source_version_id"])
                 .single().execute().data)
        version = found["version_number"] if found else None

    asset_store.configure(client, content_item_id)
    work_dir = Path(tempfile.mkdtemp(prefix="quiz-export-"))
    try:
        stats = restore_audio(data, work_dir)
        print(f"       audio restauré : {stats}")
        manifest = quiz_shorts.export_chapters(data, work_dir, work_dir / "out", [chapter])
        failed = [o for o in manifest["items"] if o["status"] != "ready"]
        if failed or not manifest["items"]:
            raise quiz_shorts.ExportError(failed[0]["error"] if failed else "Aucune sortie produite.")
        paths, outputs = {}, []
        for output in manifest["items"]:
            path = export_storage_path(content_item_id, version, output["file"])
            storage._upload(client, path, str(work_dir / "out" / output["file"]), "video/mp4")
            paths[output["file"]] = path
            outputs.append({k: output[k] for k in ("file", "part", "parts", "first_question", "last_question", "duration",
                                                   "width", "height", "bytes", "short_eligible")})
        return {"status": "ready", "outputs": outputs, "storage_paths": paths, "error": None}
    finally:
        asset_store.reset()
        shutil.rmtree(work_dir, ignore_errors=True)
