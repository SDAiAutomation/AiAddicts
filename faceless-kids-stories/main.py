#!/usr/bin/env python3
"""Point d'entrée du moteur de génération Faceless Kids Stories.

Usage :
    python main.py stories/histoire-01.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.assembler import (
    AssemblyError,
    build_block_clip,
    burn_subtitles,
    concatenate_clips,
    get_audio_duration,
)
from engine.story import load_story
from engine.subtitles import write_srt
from engine.tts import TTSError, generate_voiceover
from engine.video import VideoGenerationError, generate_video_clip

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def generate_story(story_path: str) -> Path:
    story = load_story(story_path)
    print(f"Histoire : {story.title} ({len(story.blocks)} blocs)")

    audio_dir = OUTPUT_DIR / "audio"
    video_dir = OUTPUT_DIR / "video_clips"
    final_dir = OUTPUT_DIR / "final"
    tmp_dir = OUTPUT_DIR / "tmp" / story.slug

    print("Étape 1/3 — Génération des voix off (ElevenLabs)")
    audio_paths = []
    for block in story.blocks:
        out = audio_dir / f"{story.slug}_bloc{block.index:02d}.mp3"
        print(f"  Bloc {block.index}: \"{block.vo[:60]}\"")
        generate_voiceover(block.vo, story.voice_id, out)
        audio_paths.append(out)

    print("Étape 2/3 — Génération des clips vidéo (style Studio 3D, Wan 2.2 / fal.ai)")
    video_paths = []
    for block, audio_path in zip(story.blocks, audio_paths):
        duration = get_audio_duration(audio_path)
        out = video_dir / f"{story.slug}_bloc{block.index:02d}.mp4"
        print(f"  Bloc {block.index}: \"{block.visual[:60]}\" ({duration:.1f}s)")
        generate_video_clip(
            visual_prompt=block.visual,
            style_prompt=story.style_prompt,
            aspect_ratio=story.aspect_ratio,
            output_path=out,
            duration_seconds=duration,
        )
        video_paths.append(out)

    print("Étape 3/3 — Montage final (clips + voix off + sous-titres incrustés)")
    block_clips = []
    for block, video_path, audio_path in zip(story.blocks, video_paths, audio_paths):
        out = tmp_dir / f"bloc{block.index:02d}_avec_audio.mp4"
        build_block_clip(video_path, audio_path, out)
        block_clips.append(out)

    concatenated = tmp_dir / "concatene.mp4"
    concatenate_clips(block_clips, concatenated, tmp_dir)

    durations = [get_audio_duration(p) for p in audio_paths]
    srt_path = tmp_dir / f"{story.slug}.srt"
    write_srt(list(zip((b.vo for b in story.blocks), durations)), srt_path)

    final_path = final_dir / f"{story.slug}.mp4"
    burn_subtitles(concatenated, srt_path, final_path)

    print(f"Vidéo finale : {final_path}")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère une histoire vidéo complète (voix off + vidéo + montage) depuis un script JSON."
    )
    parser.add_argument("story_path", help="Chemin du fichier stories/*.json")
    args = parser.parse_args()

    try:
        generate_story(args.story_path)
    except (TTSError, VideoGenerationError, AssemblyError, FileNotFoundError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
