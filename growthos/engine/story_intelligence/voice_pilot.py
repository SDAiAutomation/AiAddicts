"""Explicit, opt-in voice pilot. Never runs from the production pipeline.

Usage (from repository root):
  python -m growthos.engine.story_intelligence.voice_pilot --story path/to/story.json --output /tmp/story-voice --neo-voice-id VOICE_ID --orion-voice-id VOICE_ID --generate

Without --generate this prints a safe preview and makes no paid requests.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .validator import validate_storyboard
from .audio_adapter import prepare_aligned_storyboard
from .voice_catalog import resolve_character_voices


def run(story_path: str, output_dir: str, voice_ids: dict[str, str], *, generate: bool = False, max_paid_shots: int = 2, catalog: list[dict] | None = None) -> dict:
    story = json.loads(Path(story_path).read_text(encoding="utf-8"))
    errors = validate_storyboard(story)
    if errors:
        raise ValueError("Invalid storyboard: " + "; ".join(errors))
    if catalog is not None:
        voice_ids = resolve_character_voices(story, catalog, voice_ids)
    speakers = {shot["speaker_id"] for shot in story["shots"]}
    missing = speakers - set(voice_ids)
    if generate and (missing or any(not voice_ids[sid].strip() for sid in speakers)):
        raise ValueError("Missing voice ID(s) for: " + ", ".join(sorted(missing or speakers)))
    if generate and (isinstance(max_paid_shots, bool) or not isinstance(max_paid_shots, int) or max_paid_shots < 1 or len(story["shots"]) > max_paid_shots):
        raise ValueError("Paid generation shot limit exceeded; increase --max-paid-shots explicitly")
    if not generate:
        return {"mode": "preview", "paid_requests": 0, "shot_count": len(story["shots"]), "speaker_ids": sorted(speakers), "target_duration_s": story["target_duration_s"]}
    if not os.environ.get("ELEVENLABS_API_KEY"):
        raise RuntimeError("ELEVENLABS_API_KEY is required; no requests made")
    from growthos.engine.tts import synthesize_with_timestamps
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    audio_paths = {}
    for shot in story["shots"]:
        shot_id = shot["id"]
        path = directory / (shot_id + ".mp3")
        # Do not write API keys or voice IDs to reports.
        synthesize_with_timestamps(shot["dialogue"], voice_ids[shot["speaker_id"]], str(path))
        audio_paths[shot_id] = str(path)
    aligned, report = prepare_aligned_storyboard(story, audio_paths)
    (directory / "aligned_storyboard.json").write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "timing_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"mode": "generated", "shot_count": len(story["shots"]), "report": report, "output_dir": str(directory)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in Faceloop Story Intelligence voice pilot")
    parser.add_argument("--story", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--neo-voice-id", default="", help="Legacy pilot shortcut")
    parser.add_argument("--orion-voice-id", default="", help="Legacy pilot shortcut")
    parser.add_argument("--voice-selections", help="JSON file mapping character IDs to existing catalog voice IDs")
    parser.add_argument("--voice-catalog", help="JSON file with authorized, tenant-scoped catalog entries")
    parser.add_argument("--generate", action="store_true", help="Explicitly allow paid ElevenLabs TTS calls")
    parser.add_argument("--max-paid-shots", type=int, default=2, help="Maximum number of paid TTS calls allowed (default: 2)")
    args = parser.parse_args()
    if bool(args.voice_selections) != bool(args.voice_catalog):
        parser.error("--voice-selections and --voice-catalog must be provided together")
    if args.voice_selections:
        selections = json.loads(Path(args.voice_selections).read_text(encoding="utf-8"))
        catalog = json.loads(Path(args.voice_catalog).read_text(encoding="utf-8"))
    else:
        selections = {"neo": args.neo_voice_id, "orion": args.orion_voice_id}
        catalog = None
    result = run(args.story, args.output, selections, generate=args.generate, max_paid_shots=args.max_paid_shots, catalog=catalog)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
