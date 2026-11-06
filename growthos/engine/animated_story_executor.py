"""Opt-in animated story execution with injectable voice and shot providers.

This module does not select a paid video vendor or publish content.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol
import shutil

from .animated_story_plan import RenderPlan, RenderTask

class ShotRenderer(Protocol):
    def render(self, task: RenderTask, output_path: Path) -> Path: ...

class VoiceRenderer(Protocol):
    def render(self, text: str, voice_id: str, output_path: Path) -> Path: ...

@dataclass(frozen=True)
class ShotArtifact:
    shot_id: str
    video_path: Path
    audio_path: Path | None

class ElevenLabsVoiceRenderer:
    """Adapter around the existing TTS integration. Paid calls are opt-in."""
    def render(self, text: str, voice_id: str, output_path: Path) -> Path:
        from .tts import synthesize
        synthesize(text, voice_id, str(output_path))
        return output_path

class ExistingClipRenderer:
    """Use pre-rendered licensed clips for a zero-video-API pilot.

    Every shot must have a supplied clip; no stock content is silently substituted.
    """
    def __init__(self, clips: dict[str, Path]):
        self.clips = clips

    def render(self, task: RenderTask, output_path: Path) -> Path:
        source = self.clips.get(task.shot_id)
        if source is None or not source.is_file():
            raise FileNotFoundError(f"missing_clip:{task.shot_id}")
        if source.resolve() == output_path.resolve():
            return output_path
        shutil.copyfile(source, output_path)
        return output_path

def execute_plan(
    plan: RenderPlan,
    output_dir: Path,
    *,
    shot_renderer: ShotRenderer,
    voice_renderer: VoiceRenderer | None = None,
    authorize_paid_calls: bool = False,
    before_paid_call: Callable[[str, RenderTask], None] | None = None,
) -> tuple[ShotArtifact, ...]:
    """Execute a plan into an isolated folder.

    Providers are explicitly injected. Voice synthesis requires opt-in and a
    per-call authorization hook; no implicit spend or publication.
    """
    output_dir = Path(output_dir)
    if voice_renderer is not None and not authorize_paid_calls:
        raise PermissionError("paid_voice_calls_not_authorized")
    if voice_renderer is not None and before_paid_call is None:
        raise PermissionError("missing_per_call_budget_guard")
    if not plan.tasks:
        raise ValueError("empty_render_plan")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[ShotArtifact] = []
    for task in plan.tasks:
        # Keyed filenames make retries idempotent within a single job directory.
        prefix = f"{task.cache_key}"
        video_path = output_dir / f"{prefix}.mp4"
        audio_path = output_dir / f"{prefix}.mp3" if task.dialogue else None
        if not video_path.is_file() or video_path.stat().st_size == 0:
            result = Path(shot_renderer.render(task, video_path))
            if result.resolve() != video_path.resolve() or not video_path.is_file() or video_path.stat().st_size == 0:
                raise RuntimeError(f"invalid_video_output:{task.shot_id}")
        if audio_path is not None:
            if not task.speaker_voice_id:
                raise ValueError(f"missing_voice:{task.shot_id}")
            if voice_renderer is None:
                raise ValueError(f"missing_voice_renderer:{task.shot_id}")
            if not audio_path.is_file() or audio_path.stat().st_size == 0:
                before_paid_call("voice", task)
                result = Path(voice_renderer.render(task.dialogue, task.speaker_voice_id, audio_path))
                if result.resolve() != audio_path.resolve() or not audio_path.is_file() or audio_path.stat().st_size == 0:
                    raise RuntimeError(f"invalid_audio_output:{task.shot_id}")
        artifacts.append(ShotArtifact(task.shot_id, video_path, audio_path))
    return tuple(artifacts)
