"""Chargement et validation des scripts d'histoire (stories/*.json)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

REQUIRED_STORY_FIELDS = ("title", "theme", "voice_id", "aspect_ratio", "style_prompt", "blocks")
REQUIRED_BLOCK_FIELDS = ("vo", "visual")
VALID_ASPECT_RATIOS = ("9:16", "16:9", "1:1")


@dataclass
class Block:
    index: int
    vo: str
    visual: str


@dataclass
class Story:
    title: str
    theme: str
    voice_id: str
    aspect_ratio: str
    style_prompt: str
    blocks: List[Block]
    slug: str


def slugify(title: str) -> str:
    chars = [c.lower() if c.isalnum() else "-" for c in title]
    slug = "".join(chars)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "histoire"


def load_story(path: Union[str, Path]) -> Story:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Script d'histoire introuvable : {path}")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    missing = [field for field in REQUIRED_STORY_FIELDS if field not in data]
    if missing:
        raise ValueError(f"Champs manquants dans {path.name} : {', '.join(missing)}")

    if data["aspect_ratio"] not in VALID_ASPECT_RATIOS:
        raise ValueError(
            f"aspect_ratio invalide : {data['aspect_ratio']!r} "
            f"(attendu : {', '.join(VALID_ASPECT_RATIOS)})"
        )

    if not isinstance(data["blocks"], list) or not data["blocks"]:
        raise ValueError(f"{path.name} doit contenir au moins un bloc dans 'blocks'")

    blocks = []
    for i, raw_block in enumerate(data["blocks"]):
        missing_block = [f for f in REQUIRED_BLOCK_FIELDS if f not in raw_block]
        if missing_block:
            raise ValueError(f"Bloc {i} : champs manquants : {', '.join(missing_block)}")
        blocks.append(Block(index=i, vo=raw_block["vo"], visual=raw_block["visual"]))

    return Story(
        title=data["title"],
        theme=data["theme"],
        voice_id=data["voice_id"],
        aspect_ratio=data["aspect_ratio"],
        style_prompt=data["style_prompt"],
        blocks=blocks,
        slug=slugify(data["title"]),
    )
