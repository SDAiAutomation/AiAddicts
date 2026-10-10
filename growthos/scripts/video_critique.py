"""Critique de la VIDEO RENDUE, mode observation : planche contact -> note par critere -> JSON.
N'agit sur rien (ni re-rendu, ni base, ni quality_check). Usage : python scripts/video_critique.py video.mp4 [...]
Modele = IMAGE_QC_MODEL ; cout estime avec SCRIPT_PRICE_IN/OUT_PER_M (meme classe de modele, a confirmer)."""
import base64, json, os, subprocess, sys, tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CRITERIA = ("hook", "readability", "motion", "variety", "composition", "sync_visual")
FRAMES = 12
PROMPT = (
    "Tu juges une video verticale courte a partir d'une planche contact de 12 images regulierement espacees "
    "(ordre de lecture gauche->droite, haut->bas). Note chaque critere de 0 a 10 : hook (la 1re image donne-t-elle "
    "envie de rester), readability (texte lisible sur telephone, pas de debordement), motion (variete et dynamisme "
    "visibles, pas un diaporama), variety (images/mises en page differentes), composition (zones sures, equilibre), "
    "sync_visual (le visuel semble-t-il raconter la meme chose d'une image a l'autre). Reponds UNIQUEMENT en JSON : "
    '{"scores": {"hook":0,"readability":0,"motion":0,"variety":0,"composition":0,"sync_visual":0}, '
    '"worst": [{"criterion":"","frame":1,"issue":""}]} avec au plus 3 elements dans worst, frame = numero 1-12.'
)


def parse(raw: dict) -> dict | None:
    """Valide la reponse du juge ; None si inexploitable."""
    scores = raw.get("scores") if isinstance(raw, dict) else None
    if not isinstance(scores, dict):
        return None
    out = {}
    for k in CRITERIA:
        try:
            out[k] = max(0, min(10, int(scores[k])))
        except (KeyError, TypeError, ValueError):
            return None
    worst = [w for w in raw.get("worst", []) if isinstance(w, dict)][:3] if isinstance(raw.get("worst"), list) else []
    return {"scores": out, "average": round(sum(out.values()) / len(out), 1), "worst": worst}


def contact_sheet(video: str, out: str) -> float:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True, check=True).stdout)
    fps = FRAMES / dur
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vf",
                    f"fps={fps:.5f},scale=270:480,tile=6x2",
                    "-frames:v", "1", out], check=True)
    return dur


def critique(video: str, model: str, key: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        sheet = os.path.join(tmp, "sheet.jpg")
        dur = contact_sheet(video, sheet)
        b64 = base64.b64encode(Path(sheet).read_bytes()).decode()
    r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, timeout=120, json={
        "model": model, "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                      {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]})
    r.raise_for_status()
    body = r.json()
    u = body.get("usage", {})
    cost = (u.get("prompt_tokens", 0) * float(os.environ.get("SCRIPT_PRICE_IN_PER_M", 0))
            + u.get("completion_tokens", 0) * float(os.environ.get("SCRIPT_PRICE_OUT_PER_M", 0))) / 1e6
    res = parse(json.loads(body["choices"][0]["message"]["content"]))
    return {"video": Path(video).name, "duration_s": round(dur, 1), "model": model, "usage": u, "cost_usd_est": round(cost, 4), "critique": res}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf8")
    load_dotenv(ROOT / ".env")
    model, key = os.environ.get("IMAGE_QC_MODEL", "").strip(), os.environ.get("OPENAI_API_KEY", "")
    if not model or not key:
        sys.exit("IMAGE_QC_MODEL et OPENAI_API_KEY requis")
    out = ROOT / "output" / "critique"
    out.mkdir(parents=True, exist_ok=True)
    for v in sys.argv[1:]:
        res = critique(v, model, key)
        (out / (Path(v).stem[:60] + ".json")).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf8")
        print(json.dumps(res, ensure_ascii=False))
