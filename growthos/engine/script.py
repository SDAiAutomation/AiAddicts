"""Load and validate a GrowthOS content script (script.json)."""
import json
from pathlib import Path

ALLOWED_ROLES = {"hook", "point", "cta"}
REQUIRED_TOP_LEVEL = ("title", "niche", "account", "voice_id", "blocks")


def load_script(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_script(data)
    data.setdefault("aspect_ratio", "9:16")
    data.setdefault("hashtags", [])
    return data


def validate_script(data: dict) -> None:
    for field in REQUIRED_TOP_LEVEL:
        if not data.get(field):
            raise ValueError(f"champ requis manquant ou vide : '{field}'")

    blocks = data["blocks"]
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("'blocks' doit être une liste non vide")

    for i, block in enumerate(blocks):
        text = block.get("text", "").strip()
        role = block.get("role")
        if not text:
            raise ValueError(f"blocks[{i}] : 'text' manquant ou vide")
        if role not in ALLOWED_ROLES:
            raise ValueError(
                f"blocks[{i}] : role '{role}' invalide (attendu : {sorted(ALLOWED_ROLES)})"
            )


def slug(data: dict) -> str:
    base = f"{data['account']}-{data['title']}"
    keep = [c.lower() if c.isalnum() else "-" for c in base]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")
