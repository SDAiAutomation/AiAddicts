"""Build the manual-publish package: caption text + a short pre-publish checklist.

No OAuth / API publishing in this MVP on purpose: real platform publishing
means TikTok/Meta developer app review, which would stall week 1-2 of the
dogfooding plan. Manual publish is the deliberately-artisanal choice here.
"""
from pathlib import Path


def build_caption(script: dict) -> str:
    hook = next((b["text"] for b in script["blocks"] if b["role"] == "hook"), "")
    cta = script.get("cta") or next(
        (b["text"] for b in script["blocks"] if b["role"] == "cta"), ""
    )
    hashtags = " ".join(script.get("hashtags", []))
    parts = [p for p in (hook, cta, hashtags) if p]
    return "\n\n".join(parts)


def build_checklist(script: dict, video_path: str) -> str:
    return "\n".join([
        f"# Checklist de publication : {script['title']}",
        "",
        f"- [ ] Compte cible : {script['account']}",
        f"- [ ] Format vérifié ({script.get('aspect_ratio', '9:16')}) : {video_path}",
        "- [ ] Captions lisibles sans le son (relire à l'écran)",
        "- [ ] Caption et hashtags copiés depuis caption.txt",
        "- [ ] Horaire de publication choisi",
        "- [ ] Ligne ajoutée dans metrics/suivi-hebdo.csv après publication",
    ])


def write_pack(script: dict, video_path: str, out_dir: str) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    caption_path = out_dir / "caption.txt"
    checklist_path = out_dir / "checklist.md"

    caption_path.write_text(build_caption(script), encoding="utf-8")
    checklist_path.write_text(build_checklist(script, video_path), encoding="utf-8")

    return {"caption": str(caption_path), "checklist": str(checklist_path)}
