"""Renders one v2.1 story entirely on this machine through the real pipeline (contract, timeline, shot plan, rig, mix, quality).

The ONLY paid call is the ElevenLabs voice synthesis. It is protected twice: a hard cap on the characters sent (CHAR_CAP, checked
before every request), and a cache keyed by text and voice, so a re-render, a crash after the voices, or a second look never pays
for a line twice. No Faceloop credit is touched (the credit port is local), nothing is written to the database or storage, and the
moderation step is skipped because there is no content item. The key is read from the engine's private .env, never printed.

usage (from AiAddicts/growthos): python ../experiments/story_writing/run_local_story.py <story.json> <out_dir> [--cap 2000] [--dry-run]
--dry-run: validates, estimates, and renders NOTHING and calls NOTHING (prints the characters it would send)."""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path.cwd()))
from engine.story_animation import contract, measure, packs, pipeline, quality, rig_v1, voices  # noqa: E402

GODOT = r"C:\Users\user2\AppData\Local\Microsoft\WinGet\Packages\GodotEngine.GodotEngine_Microsoft.Winget.Source_8wekyb3d8bbwe\Godot_v4.7.2-stable_win64_console.exe"
PACK = Path(r"C:\Users\user2\Documents\faceloop-story-studio\AiAddicts\experiments\story_gate1\sprites")
ENV = r"C:\Users\user2\Desktop\GrowthOS\AiAddicts\growthos\.env"
# voices of the web catalogue (growthos-web voices.ts): Corentin, Matilda, and Christian Page (calm French documentary narrator)
VOICE_IDS = {"pip": "IHngRooVccHyPqB4uQkG", "rosette": "XrExE9yKIg1WjnnlVkGX", "narrator": "sCHnH1GukQg1oFEgRwoV"}


class CharCap(RuntimeError):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("out")
    ap.add_argument("--cap", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(Path(a.story).read_text(encoding="utf-8"))
    story = doc["story"]
    for c in story["characters"]:
        c["voice_id"] = VOICE_IDS[c["id"]]
    story["narrator"]["voice_id"] = VOICE_IDS["narrator"]
    chars = sum(len(s["dialogue"]) for s in story["shots"])
    errors = contract.validate_animation_story(story, pipeline.RIG_V1_CATALOG)
    print(f"story: {len(story['shots'])} shots, {chars} characters, target {story.get('duration_target_s')} s, contract errors: {errors or 'none'}")
    if errors:
        sys.exit(1)
    if chars > a.cap:
        sys.exit(f"refused: {chars} characters are above the cap of {a.cap}")
    if a.dry_run:
        print("dry run: nothing sent, nothing rendered")
        return

    if "ELEVENLABS_API_KEY" not in os.environ:
        from dotenv import dotenv_values
        os.environ["ELEVENLABS_API_KEY"] = dotenv_values(ENV)["ELEVENLABS_API_KEY"]
    cache = out / "voice_cache"
    cache.mkdir(exist_ok=True)
    sent = {"chars": 0, "requests": 0, "cached": 0}

    def synth(text, voice, wav):
        key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]
        meta, cached_wav = cache / f"{key}.json", cache / f"{key}.wav"
        if meta.is_file() and cached_wav.is_file():
            sent["cached"] += 1
            shutil.copyfile(cached_wav, wav)
            return json.loads(meta.read_text(encoding="utf-8"))
        if sent["chars"] + len(text) > a.cap:
            raise CharCap(f"cap of {a.cap} characters would be exceeded")
        sent["chars"] += len(text)
        sent["requests"] += 1
        info = voices.synthesize_line(text, voice, wav)
        shutil.copyfile(wav, cached_wav)
        meta.write_text(json.dumps(info), encoding="utf-8")
        return info

    renderer = rig_v1.RigV1Renderer(GODOT)
    expected = {"width": rig_v1.WIDTH, "height": rig_v1.HEIGHT, "fps": rig_v1.FPS}
    if story.get("duration_target_s"):
        expected["target_s"] = story["duration_target_s"]
    result = {}

    def check_quality(final):
        report = measure.measure(final)
        result["report"] = {k: report.get(k) for k in ("video_duration_s", "audio_duration_s", "width", "height", "fps", "size_bytes", "mean_volume_db", "max_volume_db")}
        return quality.judge_media(report, expected)

    def publish(final, timeline, review):
        target = out / "story.mp4"
        shutil.copyfile(final, target)
        result["review"] = [p.text for p in review]
        result["timeline_total"] = timeline["total"]
        result["lines"] = [(l["who"], round(l["start"], 2), round(l["dur"], 2), len(l["text"])) for l in timeline["lines"]]
        return {"video": str(target)}

    ports = pipeline.Ports(
        authorize=lambda: None, moderate=lambda s: None, ready=lambda: packs.validate_pack(PACK), estimate=renderer.estimate,
        reserve_credit=lambda: True, refund_credit=lambda: None, record_event=lambda *a, **k: None, synthesize=synth,
        render=lambda tl, workdir: renderer.render(tl, PACK, workdir, 1800.0),
        mix=lambda rendered, starts, tl, final: voices.mix_and_mux(rendered.video_path, starts, tl["total"], final),
        check_quality=check_quality, publish=publish, catalog=pipeline.RIG_V1_CATALOG, usd_per_1k_chars=0.18,
        progress=lambda label: print("  step:", label, flush=True),
    )
    try:
        pipeline.run(doc, ports, out / "work")
    finally:
        print(f"ElevenLabs: {sent['requests']} requests, {sent['chars']} characters sent, {sent['cached']} lines from cache", flush=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
