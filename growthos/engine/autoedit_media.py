"""Analyse locale et rendu FFmpeg pour AutoEdit Sports.

Ce jalon utilise uniquement des signaux mesurables et gratuits. Il détecte les
ruptures visuelles, construit l'EDL existante puis l'exécute. Il ne prétend pas
reconnaître un but, un joueur ou une action sportive sans analyse sémantique.
"""
import json
import re
from pathlib import Path

from engine import autoedit
from engine.video import _run

SCENE_THRESHOLD = 0.30
MIN_EVENT_GAP_SECONDS = 1.0
MAX_EVENTS = 80
AUDIO_MIN_GAP_SECONDS = 2.0


class SignalAnalyzer:
    name = "signals"
    simulated = False

    def analyze(self, source: autoedit.SourceVideo) -> autoedit.AnalysisResult:
        if not source.local_path:
            raise autoedit.AutoEditError(autoedit.ERR_SOURCE_MISSING, "Source locale absente.", True)
        duration = probe_duration(source.local_path)
        timestamps = detect_scene_changes(source.local_path)
        events = []
        for index, at in enumerate(timestamps[:MAX_EVENTS], start=1):
            start = max(0.0, at - 1.5)
            end = min(duration, at + 2.5)
            if end - start < 1.0:
                continue
            events.append({
                "id": f"{source.job_id}-scene-{index}",
                "type": "scene_change",
                "startSeconds": round(start, 2),
                "endSeconds": round(end, 2),
                "score": None,
                "confidence": None,
                "subject": None,
                "notes": "Rupture visuelle détectée localement par FFmpeg.",
            })
        for index, (at, score) in enumerate(detect_audio_peaks(source.local_path), start=1):
            events.append({
                "id": f"{source.job_id}-audio-{index}",
                "type": "audio_peak",
                "startSeconds": round(max(0.0, at - 1.5), 2),
                "endSeconds": round(min(duration, at + 2.5), 2),
                "score": score,
                "confidence": None,
                "subject": None,
                "notes": "Pic d'intensité audio mesuré localement par FFmpeg.",
            })
        if not events:
            step = max(3.0, duration / 8)
            for index, at in enumerate(_frange(step / 2, duration, step), start=1):
                events.append({
                    "id": f"{source.job_id}-segment-{index}", "type": "highlight",
                    "startSeconds": round(max(0.0, at - 1.5), 2),
                    "endSeconds": round(min(duration, at + 2.5), 2),
                    "score": None, "confidence": None, "subject": None,
                    "notes": "Segment régulier : aucune rupture visuelle assez forte n'a été détectée.",
                })
        return autoedit.AnalysisResult(
            events=events,
            duration_seconds=duration,
            analysis_cost=0.0,
            simulated=False,
            analyzer=self.name,
            notes=["Analyse locale limitée aux signaux visuels et audio : vérifiez les actions sportives et le joueur ciblé."],
        )


def probe_duration(path: str) -> float:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(Path(path).resolve()),
    ])
    duration = float(json.loads(result.stdout)["format"]["duration"])
    if duration <= 0:
        raise RuntimeError("durée vidéo invalide")
    return duration


def detect_scene_changes(path: str) -> list[float]:
    result = _run([
        "ffmpeg", "-i", str(Path(path).resolve()),
        "-filter:v", f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
        "-an", "-f", "null", "-",
    ])
    found = [float(value) for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr)]
    kept: list[float] = []
    for value in found:
        if not kept or value - kept[-1] >= MIN_EVENT_GAP_SECONDS:
            kept.append(value)
    return kept


def detect_audio_peaks(path: str) -> list[tuple[float, int]]:
    """Retourne les maxima RMS relatifs. Le score décrit l'intensité mesurée
    dans cette vidéo (0..100), jamais une probabilité de but ou de viralité.
    Sans piste audio : aucun pic (ffmpeg échouerait sur un filtre audio sans
    flux, ce qui faisait échouer tout le montage d'une vidéo muette)."""
    if not probe_has_audio(path):
        return []
    result = _run([
        "ffmpeg", "-i", str(Path(path).resolve()),
        "-af", f"asetnsamples=n=24000,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-vn", "-f", "null", "-",
    ])
    samples = parse_audio_levels(result.stderr)
    finite = [(at, level) for at, level in samples if level > -120]
    if len(finite) < 3:
        return []
    levels = sorted(level for _, level in finite)
    threshold = levels[max(0, int(len(levels) * 0.75) - 1)]
    low, high = levels[0], levels[-1]
    # Un public ou une musique constamment forts ne constituent pas une série
    # de moments forts. Exiger une vraie dynamique relative évite de découper
    # arbitrairement un signal presque constant.
    if high - low < 3.0:
        return []
    candidates = sorted(((at, level) for at, level in finite if level >= threshold), key=lambda item: item[1], reverse=True)
    selected: list[tuple[float, int]] = []
    for at, level in candidates:
        if any(abs(at - existing_at) < AUDIO_MIN_GAP_SECONDS for existing_at, _ in selected):
            continue
        score = 50 if high <= low else round(50 + 50 * (level - low) / (high - low))
        selected.append((at, min(100, max(0, score))))
        if len(selected) >= 20:
            break
    return sorted(selected)


def parse_audio_levels(stderr: str) -> list[tuple[float, float]]:
    current_time: float | None = None
    samples: list[tuple[float, float]] = []
    for line in stderr.splitlines():
        time_match = re.search(r"pts_time:([0-9]+(?:\.[0-9]+)?)", line)
        if time_match:
            current_time = float(time_match.group(1))
        level_match = re.search(r"lavfi\.astats\.Overall\.RMS_level=(-?(?:[0-9]+(?:\.[0-9]+)?|inf))", line, re.I)
        if level_match and current_time is not None:
            raw = level_match.group(1).lower()
            samples.append((current_time, -999.0 if raw == "-inf" else float(raw)))
    return samples


def render_plan(source_path: str, plan: dict, output_path: str) -> str:
    decisions = plan["decisions"]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    has_audio = probe_has_audio(source_path)
    for index, decision in enumerate(decisions):
        inputs += ["-ss", f"{decision['startSeconds']:.3f}", "-to", f"{decision['endSeconds']:.3f}", "-i", source_path]
        label = f"v{index}"
        style_filter = _style_filter(plan["style"])
        filters.append(
            f"[{index}:v]scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280{style_filter},setsar=1,fps=30[{label}]"
        )
        video_labels.append(f"[{label}]")
        if has_audio:
            filters.append(f"[{index}:a]asetpts=PTS-STARTPTS[a{index}]")
            audio_labels.append(f"[a{index}]")
    concat_inputs = [label for pair in zip(video_labels, audio_labels) for label in pair] if has_audio else video_labels
    filters.append(
        "".join(concat_inputs)
        + f"concat=n={len(decisions)}:v=1:a={1 if has_audio else 0}[outv]"
        + ("[outa]" if has_audio else "")
    )
    command = [
        "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        command += ["-map", "[outa]", "-c:a", "aac", "-b:a", "160k"]
    command += ["-movflags", "+faststart", str(output)]
    _run(command)
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("FFmpeg n'a produit aucun montage")
    return str(output)


def probe_has_audio(path: str) -> bool:
    result = _run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=index", "-of", "json", str(Path(path).resolve()),
    ])
    return bool(json.loads(result.stdout).get("streams"))


def _style_filter(style: str) -> str:
    return {
        "hype": ",eq=saturation=1.25:contrast=1.08",
        "cinematic": ",eq=saturation=0.90:contrast=1.10:brightness=-0.02",
        "emotional": ",eq=saturation=0.95:contrast=1.04:gamma=0.98",
        "clean": "",
    }.get(style, "")


def _frange(start: float, stop: float, step: float):
    value = start
    while value < stop:
        yield value
        value += step
