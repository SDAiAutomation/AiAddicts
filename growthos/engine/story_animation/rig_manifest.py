"""Validated cutout rig data. Manifests contain geometry and asset identities, never paths or scripts.

This is an input boundary for the next renderer version. The existing rig_v1 pilot
continues to use its packaged Pip/Rosette scene until that renderer consumes this
contract; merely validating a manifest does not make a character renderable.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from . import packs
from .renderer import RenderError

SCHEMA_VERSION = 1
RIG_TYPE = "cutout_2d"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ASSETS = 12
MAX_PIXELS = 2048 * 2048
MAX_TOTAL_PIXELS = 8_000_000
_ID = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ANCHORS = frozenset(("hip", "neck", "shoulder_l", "shoulder_r", "hip_l", "hip_r", "wrist_l", "wrist_r", "ankle_l", "ankle_r"))
SPRITES = frozenset(("torso", "head", "hand_l", "hand_r", "foot_l", "foot_r"))
EXPRESSIONS = frozenset(("neutral", "happy", "sad", "angry", "surprised"))
ACTIONS = frozenset(("idle", "walk", "run", "talk", "point", "react"))
MOUTHS = frozenset(("closed", "open", "round"))


class RigManifestError(ValueError):
    """A rig has unsafe or incomplete data. Messages contain no paths or secrets."""


def _number(value: object, low: float, high: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _point(value: object) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(_number(n, -4096, 4096) for n in value)


def validate_manifest(raw: object) -> dict:
    """Return a strictly validated manifest; reject unrecognized fields and executable data."""
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "character_id", "rig_type", "canvas", "anchors", "face", "sprites", "assets", "expressions", "actions", "mouths"}:
        raise RigManifestError("rig manifest fields are invalid")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
        raise RigManifestError("unsupported rig schema version")
    if not _id(raw["character_id"]) or raw["rig_type"] != RIG_TYPE:
        raise RigManifestError("invalid character id or rig type")
    canvas = raw["canvas"]
    if not isinstance(canvas, list) or len(canvas) != 2 or not all(type(n) is int and 1 <= n <= 4096 for n in canvas):
        raise RigManifestError("invalid rig canvas")
    anchors = raw["anchors"]
    if not isinstance(anchors, dict) or set(anchors) != ANCHORS or not all(_point(p) for p in anchors.values()):
        raise RigManifestError("rig anchors are incomplete or invalid")
    face = raw["face"]
    if not isinstance(face, dict) or set(face) != {"eye_l", "eye_r", "mouth"} or not all(_point(p) for p in face.values()):
        raise RigManifestError("rig face anchors are incomplete or invalid")
    sprites = raw["sprites"]
    if not isinstance(sprites, dict) or set(sprites) != SPRITES or not all(_id(asset_id) for asset_id in sprites.values()):
        raise RigManifestError("rig sprites are incomplete or invalid")
    assets = raw["assets"]
    if not isinstance(assets, dict) or not 1 <= len(assets) <= MAX_ASSETS or not set(sprites.values()) <= set(assets):
        raise RigManifestError("rig assets are incomplete or excessive")
    for asset_id, meta in assets.items():
        if not _id(asset_id) or not isinstance(meta, dict) or set(meta) != {"sha256", "width", "height"}:
            raise RigManifestError("rig asset entry is invalid")
        if not isinstance(meta["sha256"], str) or not _SHA256.fullmatch(meta["sha256"]):
            raise RigManifestError("rig asset hash is invalid")
        if not all(type(meta[k]) is int and 1 <= meta[k] <= 4096 for k in ("width", "height")) or meta["width"] * meta["height"] > MAX_PIXELS:
            raise RigManifestError("rig asset dimensions are invalid")
    if sum(meta["width"] * meta["height"] for meta in assets.values()) > MAX_TOTAL_PIXELS:
        raise RigManifestError("rig asset pixel budget is exceeded")
    head_asset = assets[sprites["head"]]
    if any(not 0 <= face[k][0] <= head_asset["width"] or not 0 <= face[k][1] <= head_asset["height"] for k in face):
        raise RigManifestError("rig face anchors must lie on the head sprite")
    for key, allowed in (("expressions", EXPRESSIONS), ("actions", ACTIONS), ("mouths", MOUTHS)):
        value = raw[key]
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v in allowed for v in value) or len(value) != len(set(value)):
            raise RigManifestError(f"rig {key} are invalid")
    if "neutral" not in raw["expressions"] or "idle" not in raw["actions"] or "closed" not in raw["mouths"]:
        raise RigManifestError("rig is missing required default poses")
    return raw


def load_manifest(manifest_path: Path, pack_dir: Path) -> dict:
    """Read a pack-local manifest and verify every referenced PNG within that pack."""
    manifest_path, pack_dir = Path(manifest_path), Path(pack_dir).resolve()
    if manifest_path.parent.resolve() != pack_dir or manifest_path.name != "rig.json":
        raise RigManifestError("rig manifest must be inside the approved pack")
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise RigManifestError("rig manifest file is missing or too large")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RigManifestError("rig manifest is not valid JSON") from exc
    rig = validate_manifest(raw)
    for asset_id, meta in rig["assets"].items():
        asset = pack_dir / f"{asset_id}.png"
        if asset.is_symlink() or not asset.is_file() or asset.stat().st_size > packs.MAX_FILE_BYTES:
            raise RigManifestError(f"rig asset {asset_id} is missing or oversized")
        try:
            size = packs.png_size(asset)
        except OSError as exc:
            raise RigManifestError(f"rig asset {asset_id} is unreadable") from exc
        except RenderError as exc:
            raise RigManifestError(f"rig asset {asset_id} is not a PNG") from exc
        if size != (meta["width"], meta["height"]):
            raise RigManifestError(f"rig asset {asset_id} dimensions differ")
        if hashlib.sha256(asset.read_bytes()).hexdigest() != meta["sha256"]:
            raise RigManifestError(f"rig asset {asset_id} hash differs")
    return rig
