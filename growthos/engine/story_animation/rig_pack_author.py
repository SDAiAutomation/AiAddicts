"""Offline intake of reviewed transparent PNG parts into a validated Godot rig pack.

Image generation happens outside this module. A human must select coherent art
and provide the anchors; this tool rejects opaque or empty cutouts and records
exact hashes before the existing renderer can load them.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from . import packs, rig_manifest


class ArtIntakeError(ValueError):
    pass


def author_pack(source: Path, layout: dict, destination: Path) -> dict:
    """Copy six reviewed PNGs into a new pack. Never overwrite a prior pack."""
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ArtIntakeError("destination already exists")
    if not isinstance(layout, dict) or set(layout) != {"character_id", "canvas", "anchors", "face"}:
        raise ArtIntakeError("layout needs character_id, canvas, anchors and face")
    character_id = layout["character_id"]
    if not rig_manifest._id(character_id):
        raise ArtIntakeError("character id is invalid")
    assets = {}
    paths = {}
    for role in sorted(rig_manifest.SPRITES):
        path = source / f"{role}.png"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > packs.MAX_FILE_BYTES:
            raise ArtIntakeError(f"{role} PNG is missing")
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.format != "PNG" or image.mode != "RGBA":
                    raise ArtIntakeError(f"{role} must be a transparent RGBA PNG")
                if not 1 <= image.width <= 4096 or not 1 <= image.height <= 4096 or image.width * image.height > rig_manifest.MAX_PIXELS:
                    raise ArtIntakeError(f"{role} exceeds the rig pixel budget")
                alpha = image.getchannel("A")
                bbox = alpha.getbbox()
                if bbox is None or alpha.getextrema() == (255, 255):
                    raise ArtIntakeError(f"{role} is empty or opaque")
                if bbox[0] == 0 or bbox[1] == 0 or bbox[2] == image.width or bbox[3] == image.height:
                    raise ArtIntakeError(f"{role} artwork touches the canvas edge")
                width, height = image.size
        except ArtIntakeError:
            raise
        except (OSError, ValueError) as exc:
            raise ArtIntakeError(f"{role} PNG is unreadable") from exc
        paths[role] = path
        assets[role] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "width": width, "height": height}
    manifest = {
        "schema_version": rig_manifest.SCHEMA_VERSION,
        "character_id": character_id,
        "rig_type": rig_manifest.RIG_TYPE,
        "canvas": layout["canvas"], "anchors": layout["anchors"], "face": layout["face"],
        "sprites": {role: role for role in sorted(rig_manifest.SPRITES)},
        "assets": assets,
        "expressions": sorted(rig_manifest.EXPRESSIONS),
        "actions": sorted(rig_manifest.ACTIONS),
        "mouths": sorted(rig_manifest.MOUTHS),
    }
    try:
        rig_manifest.validate_manifest(manifest)
    except rig_manifest.RigManifestError as exc:
        raise ArtIntakeError(str(exc)) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=destination.name + ".part.", dir=destination.parent) as stage_name:
        stage = Path(stage_name)
        for role, path in paths.items():
            shutil.copyfile(path, stage / f"{role}.png")
        (stage / "rig.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rig_manifest.load_manifest(stage / "rig.json", stage)
        stage.rename(destination)
    return manifest
