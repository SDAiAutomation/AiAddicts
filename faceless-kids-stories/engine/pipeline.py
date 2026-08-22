"""Pipeline complet de génération : script -> voix off -> vidéo -> montage final.

Partagé entre le CLI (main.py) et l'API asynchrone (api.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .assembler import build_block_clip, burn_subtitles, concatenate_clips, get_audio_duration
from .story import load_story
from .subtitles import write_srt
from .tts import generate_voiceover
from .video import generate_video_clip

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# Appelé à chaque étape avec (nom_étape, détail) pour suivre la progression.
ProgressCallback = Callable[[str, str], None]


def _noop(step: str, detail: str) -> None:
    return None


def generate_story(story_path: str, on_progress: Optional[ProgressCallback] = None) -> Path:
    progress = on_progress or _noop

    story = load_story(story_path)
    progress("loaded", f"{story.title} ({len(story.blocks)} blocs)")

    audio_dir = OUTPUT_DIR / "audio"
    video_dir = OUTPUT_DIR / "video_clips"
    final_dir = OUTPUT_DIR / "final"
    tmp_dir = OUTPUT_DIR / "tmp" / story.slug

    audio_paths = []
    for block in story.blocks:
        out = audio_dir / f"{story.slug}_bloc{block.index:02d}.mp3"
        progress("voiceover", f"Bloc {block.index + 1}/{len(story.blocks)} : \"{block.vo[:60]}\"")
        generate_voiceover(block.vo, story.voice_id, out)
        audio_paths.append(out)

    video_paths = []
    for block, audio_path in zip(story.blocks, audio_paths):
        duration = get_audio_duration(audio_path)
        out = video_dir / f"{story.slug}_bloc{block.index:02d}.mp4"
        progress("video", f"Bloc {block.index + 1}/{len(story.blocks)} : \"{block.visual[:60]}\" ({duration:.1f}s)")
        generate_video_clip(
            visual_prompt=block.visual,
            style_prompt=story.style_prompt,
            aspect_ratio=story.aspect_ratio,
            output_path=out,
            duration_seconds=duration,
        )
        video_paths.append(out)

    progress("assembly", "Montage final (clips + voix off + sous-titres incrustés)")
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

    progress("done", str(final_path))
    return final_path
