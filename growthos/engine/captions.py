"""Build an SRT caption file from timed blocks."""
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_cues(timed_blocks: list[tuple[str, float]], gap: float = 0.15) -> list[dict]:
    """timed_blocks: [(text, duration_seconds), ...] in playback order.
    A small `gap` between cues avoids the last word bleeding into the next block."""
    cues = []
    cursor = 0.0
    for i, (text, duration) in enumerate(timed_blocks, start=1):
        start = cursor
        end = cursor + max(duration - gap, 0.1)
        cues.append({"index": i, "start": start, "text": text})
        cues[-1]["end"] = end
        cursor += duration
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
