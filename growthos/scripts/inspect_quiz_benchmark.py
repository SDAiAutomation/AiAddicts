"""Extract question, countdown, and reveal frames from benchmark MP4s."""
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "output" / "quiz-production-benchmark"


def main() -> None:
    results = json.loads((BENCHMARK / "results.json").read_text(encoding="utf-8"))
    for result in results:
        if result.get("failure"):
            raise RuntimeError(result["failure"])
        video = Path(result["videoPath"])
        report = json.loads((video.parent.parent / "quiz-presentation.json").read_text(encoding="utf-8"))
        question = next(scene for scene in report["scenes"] if scene["phase"] == "question")
        reveal = next(scene for scene in report["scenes"] if scene["phase"] == "reveal")
        moments = {
            "question": question["startSeconds"] + 3,
            "countdown": question["reflectionStartSeconds"] + 2,
            "reveal": reveal["startSeconds"] + 2,
        }
        name = f"{result['presentation']}-{'portrait' if result['aspectRatio'] == '9:16' else 'landscape'}"
        for phase, seconds in moments.items():
            output = BENCHMARK / "frames" / f"{name}-{phase}.jpg"
            output.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(seconds),
                            "-i", str(video), "-frames:v", "1", "-q:v", "2", str(output)], check=True)
            print(f"{name} {phase}: {seconds:.2f}s -> {output}")


if __name__ == "__main__":
    main()
