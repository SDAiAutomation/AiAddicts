"""Benchmark the production assembler with previously narrated quiz blocks.

Pass a directory of block-XX.mp3 and block-XX.words.json generated for
content/scripts/quiz-benchmark-history.json. No provider calls are permitted.
The 12 supplied voice files are reused, while countdown SFX, captions, clips,
and final MP4 are rebuilt by the production assembler for each configuration.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import assembler, generation_cache, script as script_module, voices


def run_case(source: dict, voice_cache: Path, presentation: str, aspect_ratio: str, output: Path) -> dict:
    data = json.loads(json.dumps(source))
    data["aspect_ratio"] = aspect_ratio
    data["platform"] = "youtube" if aspect_ratio == "16:9" else "tiktok"
    data["quiz"].update({"presentation": presentation, "theme": "vault"})
    data = script_module.normalize_script(data)
    voice_id = voices.resolve_voice(data)
    data["voice_id"] = voice_id
    work_dir = output / f"{script_module.slug(data)}-{generation_cache.fingerprint(data, voice_id)}"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, len(data["blocks"]) + 1):
        stem = f"block-{index:02d}"
        for suffix in (".mp3", ".words.json"):
            src = voice_cache / f"{stem}{suffix}"
            if not src.is_file() or src.stat().st_size == 0:
                raise FileNotFoundError(f"Narrated benchmark asset missing: {src}")
            dst = audio_dir / src.name
            if not dst.exists():
                shutil.copyfile(src, dst)
    started = time.monotonic()
    # If a cache key unexpectedly misses, fail instead of incurring paid usage.
    with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "OPENAI_API_KEY": "", "PEXELS_API_KEY": ""}), \
         patch("engine.assembler.tts.synthesize_with_timestamps", side_effect=RuntimeError("Benchmark forbids provider calls")):
        video_path, actual_dir, metrics = assembler._generate(data, str(output), None)
    elapsed = round(time.monotonic() - started, 3)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                           capture_output=True, text=True, check=True)
    report = json.loads((actual_dir / "quiz-presentation.json").read_text(encoding="utf-8"))
    return {"presentation": presentation, "aspectRatio": aspect_ratio,
            "questionCount": len(data["quiz"]["questions"]), "durationSeconds": round(float(probe.stdout), 3),
            "fileBytes": Path(video_path).stat().st_size, "elapsedSeconds": elapsed,
            "renderSeconds": report.get("renderSeconds") if metrics is not None else None,
            "reusedFinalVideo": metrics is None,
            "voiceFilesReused": len(data["blocks"]), "newProviderCalls": 0,
            "sourceVoiceCostUsd": None, "renderCostUsd": report.get("renderCostUsd"),
            "timingSource": report.get("timingSource"), "videoPath": str(video_path),
            "failure": None, "metricsAvailable": metrics is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "quiz-production-benchmark")
    parser.add_argument("--case", choices=["all", "classic-portrait", "motion-portrait",
                                           "classic-landscape", "motion-landscape"], default="all")
    args = parser.parse_args()
    source = json.loads((ROOT / "content/scripts/quiz-benchmark-history.json").read_text(encoding="utf-8"))
    cases = [(mode, aspect) for aspect in ("9:16", "16:9") for mode in ("classic", "motion")]
    if args.case != "all":
        cases = [(mode, aspect) for mode, aspect in cases
                 if f"{mode}-{'portrait' if aspect == '9:16' else 'landscape'}" == args.case]
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for mode, aspect in cases:
        print(f"Benchmark: {mode} {aspect}", flush=True)
        try:
            results.append(run_case(source, args.voice_cache, mode, aspect, args.output))
        except Exception as exc:
            results.append({"presentation": mode, "aspectRatio": aspect,
                            "failure": f"{type(exc).__name__}: {exc}"})
        (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)
    if any(result["failure"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
