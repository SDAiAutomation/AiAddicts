"""Explainer de bout en bout : sujet -> narration -> storyboard -> plans animés -> MP4 + `explainer.report.json`.

    python -m engine.explainer.pipeline "Pourquoi le ciel est bleu" out_dir [--lines lignes.json] [--voice-report voiceover.report.json] [--no-render]

Sans `--voice-report`, les timings de la voix sont ESTIMÉS (marqués comme tels au rapport) et la vidéo est rendue sans
voix. Un plan qui échoue à la validation après les itérations est remplacé par la scène Pillow équivalente, et c'est
écrit dans le rapport : jamais de repli silencieux. Plafond de coût : `EXPLAINER_LLM_BUDGET_USD` (défaut 1,20 $).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from . import RUNTIME_VERSION, animator, director, fallback, llm, prompts, render, timeline

FPS = 30
DIP = 0.3


def write_script(spend: llm.Spend, topic: str) -> dict:
    text = llm.complete(spend, "script", llm.ANIMATOR_MODEL, prompts.load("script"), f"Sujet : {topic}", max_tokens=4000, effort="medium")
    data = llm.extract_json(text)
    lines = [str(x).strip() for x in data.get("lines", []) if str(x).strip()]
    if not 6 <= len(lines) <= 18:
        raise RuntimeError(f"narration invalide : {len(lines)} phrases")
    return {"truthMode": data.get("truthMode", "fact"), "lines": lines}


def assemble_timeline_js(storyboard: dict, windows: list[dict], anchors: dict[str, dict], codes: dict[str, str | None],
                         narration: list[tuple[float, str]], total: float) -> str:
    """Une seule timeline qui met tous les plans bout à bout. Un plan en repli est vide ici (il sera remplacé par un clip)."""
    plans = []
    n = len(windows)
    for i, (plan, win) in enumerate(zip(storyboard["plans"], windows)):
        out_dip = i < n - 1 and plan.get("transitionOut", "dip") == "dip"
        in_dip = i > 0 and storyboard["plans"][i - 1].get("transitionOut", "dip") == "dip"
        code = codes.get(plan["id"]) or "S.sky('void');"
        transition = {"in": DIP if in_dip else 0, "out": DIP if out_dip else 0}
        plans.append("{id:%s,start:%s,duration:%s,anchors:%s,transition:%s,build:function(S){\n%s\n}}" % (
            json.dumps(plan["id"]), win["start"], win["duration"], json.dumps(anchors[plan["id"]]), json.dumps(transition), code))
    return "Faceloop.define({duration:%s,fps:%d,narration:%s,plans:[\n%s\n]});\n" % (
        total, FPS, json.dumps([[s, t] for s, t in narration], ensure_ascii=False), ",\n".join(plans))


def generate(topic: str, out_dir: str | Path, *, lines: list[str] | None = None, voice_report: dict | None = None,
             voice_wav: str | None = None, budget_usd: float | None = None, do_render: bool = True, log=print) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    budget = budget_usd if budget_usd is not None else float(os.environ.get("EXPLAINER_LLM_BUDGET_USD") or llm.DEFAULT_BUDGET_USD)
    spend = llm.Spend(limit_usd=budget)
    report: dict = {"topic": topic, "runtimeVersion": RUNTIME_VERSION, "promptVersions": prompts.versions(),
                    "models": {"director": llm.DIRECTOR_MODEL, "animator": llm.ANIMATOR_MODEL}, "steps": {}}
    clock = time.monotonic()

    def step(name: str) -> None:
        nonlocal clock
        now = time.monotonic()
        report["steps"][name] = round(now - clock, 1)
        clock = now

    log("[1/5] Narration…")
    if lines is None:
        script = write_script(spend, topic)
        lines, report["truthModeScript"] = script["lines"], script["truthMode"]
    report["lines"] = lines
    step("script")

    if voice_report:
        narration, words = timeline.narration_from_report(voice_report)
        report["timingsAreEstimated"] = False
    else:
        narration, words = timeline.estimate_narration(lines)
        report["timingsAreEstimated"] = True
    total = timeline.total_duration(narration, words)
    report["durationSeconds"] = total

    log("[2/5] Réalisation (storyboard)…")
    directed = director.direct(spend, topic, narration, words, total)
    storyboard = directed["storyboard"]
    report["storyboard"], report["directorAttempts"] = storyboard, directed["attempts"]
    (out / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False, indent=1), encoding="utf-8")
    step("director")

    windows = timeline.plan_windows(storyboard, narration, total)
    anchors, unresolved, jobs = {}, [], []
    for plan, win in zip(storyboard["plans"], windows):
        anchors[plan["id"]], missing = timeline.resolve_anchors(plan, win, words)
        unresolved += missing
        text = " ".join(narration[i][1] for i in plan["lines"])
        brief = animator.plan_brief(plan, win["duration"], anchors[plan["id"]], text, topic, storyboard.get("bible", {}), storyboard.get("world", {}))
        jobs.append({"brief": brief, "plan_id": plan["id"], "duration": win["duration"], "anchors": anchors[plan["id"]]})
    report["unresolvedAnchors"] = unresolved

    log(f"[3/5] Animation de {len(jobs)} plans…")
    results = animator.animate_all(spend, jobs)
    step("animator")
    codes = {r["id"]: (r["code"] if r["ok"] else None) for r in results}
    fallbacks = []
    for r, plan, win in zip(results, storyboard["plans"], windows):
        if not r["ok"]:
            fallbacks.append({"plan": r["id"], "reason": r["errors"][:5], "text": " ".join(narration[i][1] for i in plan["lines"])[:fallback.MAX_CHARS]})
    report["plans"] = [{"id": r["id"], "ok": r["ok"], "attempts": r["attempts"], "warnings": r["warnings"], "history": r["history"]} for r in results]
    report["fallbacks"] = fallbacks
    (out / "plans").mkdir(exist_ok=True)
    for r in results:
        (out / "plans" / f"{r['id']}.js").write_text(r["code"] or "", encoding="utf-8")

    timeline_js = out / "explainer.timeline.js"
    timeline_js.write_text(assemble_timeline_js(storyboard, windows, anchors, codes, narration, total), encoding="utf-8")
    report["spend"] = spend.report()

    if do_render:
        log("[4/5] Rendu…")
        mp4 = out / "explainer.mp4"
        if not fallbacks:
            rendered = asyncio.run(render.render_video_async(timeline_js, mp4, voice_wav))
        else:
            ok_ranges = [w for w, r in zip(windows, results) if r["ok"]]
            seg = asyncio.run(render.render_segments_async(timeline_js, ok_ranges, out / "segments"))
            ordered = []
            for win, r in zip(windows, results):
                if r["ok"]:
                    ordered.append(seg["segments"][win["id"]])
                else:
                    ordered.append(fallback.pillow_clip(next(f["text"] for f in fallbacks if f["plan"] == win["id"]), win["duration"], out / "segments" / f"fallback-{win['id']}.mp4"))
            render.assemble_segments(ordered, seg["sfx_wav"], mp4, voice_wav, out / "segments")
            rendered = {"runtimeVersion": RUNTIME_VERSION, "chromium": seg["chromium"], "durationSeconds": seg["duration"], "fps": seg["fps"]}
        report["render"], report["video"] = rendered, str(mp4)
        step("render")
    report["steps"]["totalSeconds"] = round(sum(report["steps"].values()), 1)
    (out / "explainer.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"[5/5] Terminé — coût LLM {spend.total_usd:.2f} $ (plafond {budget:.2f} $), {len(fallbacks)} repli(s), rapport : {out / 'explainer.report.json'}")
    return report


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    if len(argv) < 2:
        print(__doc__)
        return 2
    lines = json.loads(Path(argv[argv.index("--lines") + 1]).read_text(encoding="utf-8")) if "--lines" in argv else None
    voice_report = json.loads(Path(argv[argv.index("--voice-report") + 1]).read_text(encoding="utf-8")) if "--voice-report" in argv else None
    voice_wav = voice_report["wav"] if voice_report else None
    generate(argv[0], argv[1], lines=lines, voice_report=voice_report, voice_wav=voice_wav, do_render="--no-render" not in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
