"""Worker job: render the vertical exports of one chapter of a rendered five-level quiz.

Runs on an ephemeral worker, so nothing from the master render is assumed to exist on disk: the narration of every
block is restored from the asset cache (same key as the master render, see assembler.voice_text_for) and the
countdown-padded audio is rebuilt with the shared helper. The job NEVER synthesizes a voice: a cache miss fails the
export with an actionable message instead of silently spending money on a voice that could differ from the master.

Isolation: one private temp directory per job (random name), removed on exit; storage paths are derived from the
content item id and the exported version only; the browser never receives storage paths (the site signs access
after reading the row under RLS).
"""
from __future__ import annotations

import json
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


def restore_audio(data: dict, work_dir: Path) -> None:
    """Rebuild `work_dir/audio` for every block from the asset cache. Raises ExportError on any miss."""
    voice_id = data.get("voice_id")
    if not voice_id:
        raise quiz_shorts.ExportError("Voix du master inconnue : régénère la vidéo complète.")
    (work_dir / "audio").mkdir(parents=True, exist_ok=True)
    for index, block in enumerate(data["blocks"], 1):
        raw = work_dir / "audio" / f"block-{index:02d}.mp3"
        words = work_dir / "audio" / f"block-{index:02d}.words.json"
        key = asset_store.make_key(kind="voice", text=assembler.voice_text_for(data, block), voice_id=voice_id,
                                   model=tts.TTS_MODEL_ID, settings=tts.TTS_VOICE_SETTINGS)
        if not asset_store.restore_voice(key, raw, words):
            raise quiz_shorts.ExportError("Voix du master introuvable dans le cache : régénère la vidéo complète.")
        if float(block.get("hold_after_seconds") or 0) > 0:
            quiz_shorts.ensure_padded_audio(block, raw, quiz_shorts.audio_path(work_dir, index, block))


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
        restore_audio(data, work_dir)
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
