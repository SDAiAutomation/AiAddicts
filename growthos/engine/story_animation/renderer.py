"""Renderer interface for animated stories (not wired into the worker).

A renderer turns a measured timeline plus an approved asset pack into a SILENT clip; mixing, quality control and
publication stay common to every renderer. `estimate` has no side effect and is meant to run before any credit is reserved.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class RenderError(RuntimeError):
    """A render failed or was refused; the message is safe to log (no prompts, no secrets, no signed URLs)."""


@dataclass(frozen=True)
class CostEstimate:
    render_seconds: float      # wall-clock estimate, NOT a measurement
    tts_chars: int             # characters sent to the voice provider
    provider_calls: int        # paid provider calls at render time (voices only for rig_v1)
    estimated: bool = True     # always an estimate, never an invoice


@dataclass(frozen=True)
class RenderResult:
    video_path: Path
    render_seconds: float      # measured: renderer process
    encode_seconds: float      # measured: encoding
    frames: int
    width: int
    height: int
    fps: int


class StoryAnimationRenderer(Protocol):
    name: str
    version: str

    def estimate(self, total_seconds: float, tts_chars: int) -> CostEstimate: ...

    def render(self, timeline: dict, pack_dir: Path, workdir: Path, timeout_s: float) -> RenderResult: ...
