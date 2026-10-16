"""Critique de l'Explainer : (1) vérité de la narration, (2) relecture visuelle de chaque plan sur une planche d'images clés.

Le critique note chaque plan sur la grille de qualité (docs/explainer-plan.md §6). Un plan sous `THRESHOLD` de moyenne
est retravaillé par l'animateur avec les corrections demandées ; on garde TOUJOURS la meilleure version notée, jamais
une version qui régresse. Synchronisation et son ne se jugent pas sur des images fixes : ils restent `None` (inconnus),
jamais 0.
"""
from __future__ import annotations

import asyncio
import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import llm, prompts, render

THRESHOLD = 4.0
MAX_ITERATIONS = 2
SHEET_FRAMES = 6
CELL = (360, 640)
CRITERIA = ("hook", "continuite", "synchro", "lisibilite", "clarte", "rythme", "finition", "son", "justesse")


def fact_check(spend: llm.Spend, lines: list[str]) -> dict:
    """Vérité de la narration. Renvoie {verdict, flags}. Une réponse inutilisable donne 'inconnu' (jamais 'ok' par défaut)."""
    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(lines))
    try:
        data = llm.extract_json(llm.complete(spend, "factcheck", llm.ANIMATOR_MODEL, prompts.load("factcheck"), numbered, max_tokens=3000, effort="medium"))
    except (ValueError, RuntimeError) as exc:
        return {"verdict": "inconnu", "flags": [], "error": str(exc)[:200]}
    return {"verdict": data.get("verdict", "inconnu"), "flags": data.get("flags", [])}


def plan_times(window: dict, anchors: dict[str, float]) -> list[float]:
    """Instants LOCAUX échantillonnés pour la planche : début, ancres (+0,4 s), milieu, fin."""
    d = window["duration"]
    base = [0.3, d * 0.5, d - 0.3] + [min(d - 0.2, a + 0.4) for a in sorted(anchors.values())]
    picked = sorted({round(max(0.1, min(t, d - 0.1)), 2) for t in base})
    while len(picked) > SHEET_FRAMES:   # on garde le début et la fin, on retire le plus proche voisin
        gaps = [(picked[i + 1] - picked[i - 1], i) for i in range(1, len(picked) - 1)]
        picked.pop(min(gaps)[1])
    return picked


def build_sheets(timeline_js: str | Path, windows: list[dict], anchors: dict[str, dict], plan_ids: list[str], out_dir: str | Path) -> dict[str, tuple[Path, list[float]]]:
    """Une planche JPEG par plan (3 colonnes × 2 lignes, instants écrits sur chaque image). Un seul lancement de Chromium."""
    from PIL import Image, ImageDraw

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    by_id = {w["id"]: w for w in windows}
    wanted = {pid: plan_times(by_id[pid], anchors.get(pid, {})) for pid in plan_ids}
    absolute = sorted({round(by_id[pid]["start"] + t, 2) for pid, ts in wanted.items() for t in ts})
    files = asyncio.run(render.render_stills_async(timeline_js, absolute, out / "frames", fmt="jpeg"))
    path_of = {round(float(p.stem[1:]), 2): p for p in files}
    sheets = {}
    for pid, times in wanted.items():
        sheet = Image.new("RGB", (CELL[0] * 3, CELL[1] * 2), (0, 0, 0))
        for i, t in enumerate(times):
            cell = Image.open(path_of[round(by_id[pid]["start"] + t, 2)]).convert("RGB").resize(CELL)
            ImageDraw.Draw(cell).text((10, CELL[1] - 24), f"image {i + 1}  t = {t:.1f} s", fill=(255, 255, 255))
            sheet.paste(cell, ((i % 3) * CELL[0], (i // 3) * CELL[1]))
        path = out / f"sheet-{pid}.jpg"
        sheet.save(path, quality=85)
        sheets[pid] = (path, times)
    return sheets


def average(scores: dict) -> float | None:
    values = [v for k, v in scores.items() if k in CRITERIA and isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(values) / len(values), 2) if values else None


def critique_sheet(spend: llm.Spend, plan_id: str, intent: str, narration: str, sheet: Path, times: list[float], step: str) -> dict:
    image = base64.standard_b64encode(sheet.read_bytes()).decode("ascii")
    text = (f"Plan « {plan_id} ». Intention : {intent}\nNarration illustrée : {narration}\n"
            f"La planche montre {len(times)} images clés (instants : {', '.join(f'{t:.1f} s' for t in times)}).")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}}, {"type": "text", "text": text}]
    try:
        data = llm.extract_json(llm.complete(spend, step, llm.ANIMATOR_MODEL, prompts.load("critic"), content, max_tokens=2500, effort="medium"))
    except (ValueError, RuntimeError) as exc:
        return {"plan": plan_id, "scores": {}, "average": None, "issues": [], "facts": [], "error": str(exc)[:200]}
    scores = {k: data.get("scores", {}).get(k) for k in CRITERIA}
    return {"plan": plan_id, "scores": scores, "average": average(scores), "issues": data.get("issues", [])[:4], "facts": data.get("faits", [])}


def critique_all(spend: llm.Spend, jobs: list[dict], workers: int = 3) -> list[dict]:
    """`jobs` : [{plan_id, intent, narration, sheet, times, step}]."""
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs)))) as pool:
        return [f.result() for f in [pool.submit(critique_sheet, spend, j["plan_id"], j["intent"], j["narration"], j["sheet"], j["times"], j["step"]) for j in jobs]]


def needs_work(critique: dict) -> bool:
    return critique["average"] is not None and critique["average"] < THRESHOLD and bool(critique["issues"])


def issues_text(critique: dict) -> str:
    return "\n".join(f"- [{i.get('critere')}] image {i.get('image')} : {i.get('probleme')} → {i.get('correction')}" for i in critique["issues"])
