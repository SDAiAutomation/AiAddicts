"""Offline end-to-end render of a 50-question five-level quiz (no provider call, synthetic narration).

Builds a deterministic arithmetic quiz, synthesizes PLACEHOLDER narration (tone bursts whose length follows the
spoken text, so timing is realistic but nothing is intelligible), then runs the real pipeline pieces: countdown
SFX, measured durations, ASS captions, FFmpeg render of the 16:9 master and the vertical chapter exports.

Run: python scripts/render_quiz50_sample.py --out /tmp/quiz50 [--lang en] [--theme studio] [--skip-master]
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import captions, quiz_chapter_export, quiz_motion, quiz_shorts, tts, video  # noqa: E402
from engine.quiz import compile_quiz  # noqa: E402


def sample_script(lang: str, theme: str) -> dict:
    questions = []
    for i in range(1, 51):
        level = (i - 1) // 10 + 1
        a, b = [(3, 4), (12, 7), (23, 17), (48, 36), (127, 83)][level - 1]
        a, b = a + i, b + (i % 5)
        correct = a * b
        options = [correct, correct + 10, correct - 7, correct + 100]
        order = [(correct * 7 + i * 3 + k) % 4 for k in range(4)]
        choices = [str(options[k]) for k in sorted(range(4), key=lambda k: order[k])]
        questions.append({
            "question": (f"What is {a} × {b}?" if lang == "en" else f"Combien font {a} × {b} ?"),
            "choices": choices, "correct_choice": choices.index(str(correct)),
            "explanation": (f"{a} times {b} equals {correct}." if lang == "en" else f"{a} fois {b} égale {correct}."),
            "countdown_seconds": 5,
        })
    return {"title": "Quiz 50 sample", "niche": "math", "account": "sample", "language": lang,
            "content_format": "quiz", "aspect_ratio": "16:9",
            "quiz": {"recipe": "long", "topic": "Multiplication", "difficulty": "progressive", "theme": theme,
                     "presentation": "motion", "chapter_mode": "five_levels", "illustrations": False,
                     "questions": questions}}


def fake_voice(text: str, path: Path) -> None:
    seconds = max(1.2, len(text) / 14.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=190:duration={seconds:.3f}",
                    "-af", "tremolo=f=4.5:d=0.8,volume=0.25", "-c:a", "libmp3lame", "-q:a", "4", str(path)],
                   check=True, capture_output=True)
    words = text.split()
    step = seconds / max(1, len(words))
    path.with_suffix(".words.json").write_text(json.dumps(
        [{"text": w, "start": round(i * step, 3), "end": round((i + 1) * step - 0.02, 3)} for i, w in enumerate(words)]),
        encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--theme", default="studio")
    ap.add_argument("--skip-master", action="store_true")
    ap.add_argument("--chapters", default="1,2,3,4,5")
    args = ap.parse_args()
    work = Path(args.out).resolve()
    work.mkdir(parents=True, exist_ok=True)
    data = compile_quiz(sample_script(args.lang, args.theme))
    blocks = data["blocks"]

    durations = []
    for i, block in enumerate(blocks, 1):
        raw = work / "audio" / f"block-{i:02d}.mp3"
        if not raw.exists():
            fake_voice(block["text"], raw)
        hold = float(block.get("hold_after_seconds") or 0)
        beat = float(block.get("quiz_reveal_beat_seconds") or 0) if hold > 0 else 0.0
        final = quiz_shorts.audio_path(work, i, block)
        if hold > 0 and not final.exists():
            video.add_countdown_sfx(str(raw), tts.get_duration_seconds(str(raw)), int(hold), str(final),
                                    str(block.get("quiz_sound_effects") or "automatic"), str(block.get("quiz_theme") or "studio"), beat)
        durations.append(tts.get_playback_duration_seconds(str(final)))
    report = quiz_motion.build_timeline(data, durations)
    segments = quiz_chapter_export.chapter_segments(quiz_chapter_export.scenes_from_timeline(report, blocks))
    (work / "chapters.json").write_text(json.dumps(segments, indent=2), encoding="utf-8")
    print("master duration", report["totalDurationSeconds"], "chapters", [(s["label"], round(s["start"], 1), round(s["end"], 1)) for s in segments])

    if not args.skip_master:
        full = video.concat_audio([str(quiz_shorts.audio_path(work, i, b)) for i, b in enumerate(blocks, 1)], str(work / "audio" / "full.wav"))
        cues = captions.build_cues([(json.loads((work / "audio" / f"block-{i:02d}.words.json").read_text()), d)
                                    for i, d in enumerate(durations, 1)], block_roles=[b.get("role", "") for b in blocks])
        bgs = [quiz_motion.base_background_for(data, 0.0, b) for b in blocks]
        cblocks = [{**b, "quiz_base_background": "#" + c[2:].lower()} if c else b for b, c in zip(blocks, bgs)]
        ass = captions.write_ass(cues, str(work / "captions.ass"), captions.caption_style_or_default(None), "1920x1080",
                                 blocks=cblocks, block_durations=durations,
                                 font=quiz_motion.BRAND_FONT if quiz_motion.brand_font_available() else None)
        video.render_final(full, ass, str(work / "master.mp4"), durations, aspect_ratio="16:9", bg_colors=bgs,
                           fonts_dir=str(quiz_motion.FONT_DIR))
        print("master rendered", quiz_shorts.probe(work / "master.mp4"))

    manifest = quiz_shorts.export_chapters(data, work, work / "shorts", [int(c) for c in args.chapters.split(",")],
                                           on_progress=print)
    print(json.dumps(manifest, indent=2))
    (work / "script.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
