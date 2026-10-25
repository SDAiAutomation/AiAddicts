"""Fetch an approved asset pack from a PRIVATE bucket and verify it against a SHA-256 manifest (not wired into any worker).

Why a manifest: sprites are not in Git and the runner has no pack of its own. Everything downloaded is checked
(exact file list, byte size, SHA-256) and then validated as a pack before it replaces anything, so a tampered, partial or
swapped object can never reach the renderer. Object paths are built here from a validated pack id and a fixed list of
names: nothing in a story, a manifest or an environment value can introduce another path.

Bucket layout (private, service-role access only; see growthos/supabase/pending/story_packs_bucket.sql):
  story-packs/<pack_id>/manifest.json
  story-packs/<pack_id>/<sprite>.png        (one object per entry of packs.REQUIRED_SPRITES)
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from . import packs, rig_manifest

BUCKET = "story-packs"
_PACK_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,40}")
_SHA = re.compile(r"[0-9a-f]{64}")
_FILE_NAMES = frozenset(f"{name}.png" for name in packs.REQUIRED_SPRITES)


class PackError(RuntimeError):
    """The pack could not be fetched or did not match its manifest; the message is safe to log."""


def check_pack_id(pack_id: str) -> str:
    if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
        raise PackError("pack id must be 1-41 lowercase letters, digits, '_' or '-'")
    return pack_id


def build_manifest(pack_dir: Path, pack_id: str, version: int = 1) -> dict:
    """Manifest of a local pack (to publish next to its files). Refuses a pack that is not valid."""
    check_pack_id(pack_id)
    problems = packs.validate_pack(Path(pack_dir))
    if problems:
        raise PackError("pack is not valid: " + "; ".join(problems[:5]))
    files = {}
    for name in sorted(_FILE_NAMES):
        data = (Path(pack_dir) / name).read_bytes()
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return {"pack_id": pack_id, "version": version, "files": files}


def parse_manifest(obj, pack_id: str) -> dict:
    """Validated manifest or PackError. The file list must be EXACTLY the required one."""
    check_pack_id(pack_id)
    if not isinstance(obj, dict) or set(obj) != {"pack_id", "version", "files"}:
        raise PackError("manifest must have exactly pack_id, version and files")
    if obj["pack_id"] != pack_id:
        raise PackError("manifest is for another pack")
    if isinstance(obj["version"], bool) or not isinstance(obj["version"], int) or obj["version"] < 1:
        raise PackError("manifest version must be a positive integer")
    files = obj["files"]
    if not isinstance(files, dict) or set(files) != _FILE_NAMES:
        raise PackError("manifest does not list exactly the required files")
    for name, meta in files.items():
        if not isinstance(meta, dict) or set(meta) != {"sha256", "bytes"}:
            raise PackError(f"manifest entry {name} is malformed")
        size = meta["bytes"]
        if not isinstance(meta["sha256"], str) or not _SHA.fullmatch(meta["sha256"]):
            raise PackError(f"manifest entry {name} has an invalid sha256")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= packs.MAX_FILE_BYTES:
            raise PackError(f"manifest entry {name} has an invalid size")
    return obj


def fetch_pack(download: Callable[[str], bytes], pack_id: str, dest: Path) -> dict:
    """Download, verify and install a pack into `dest` (replaced atomically); returns the manifest.
    `download(path)` returns the bytes of one object of the private bucket (the bucket's own size limit bounds each file)."""
    check_pack_id(pack_id)
    dest = Path(dest)
    try:
        manifest = parse_manifest(json.loads(download(f"{pack_id}/manifest.json")), pack_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PackError("manifest is not valid JSON") from exc
    part = dest.parent / (dest.name + ".part")
    if part.exists():
        shutil.rmtree(part)
    part.mkdir(parents=True)
    try:
        for name, meta in manifest["files"].items():
            data = download(f"{pack_id}/{name}")
            if len(data) != meta["bytes"] or hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise PackError(f"{name} does not match the manifest")
            (part / name).write_bytes(data)
        problems = packs.validate_pack(part)
        if problems:
            raise PackError("downloaded pack is not valid: " + "; ".join(problems[:3]))
        if dest.exists():
            shutil.rmtree(dest)
        part.rename(dest)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return manifest


def fetch_rig_pack(download: Callable[[str], bytes], character_id: str, dest: Path) -> dict:
    """Fetch a versioned character rig from the private bucket into a new job-local directory.

    The manifest may provide geometry and hashes but never an object path. Object names
    are built here only after strict ID validation. The destination is immutable once
    installed, so a concurrent render cannot observe a swapped asset.
    """
    check_pack_id(character_id)
    dest = Path(dest)
    if dest.exists() or dest.is_symlink():
        raise PackError("rig pack destination already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = download(f"{character_id}/rig.json")
    if not isinstance(raw, bytes) or len(raw) > rig_manifest.MAX_MANIFEST_BYTES:
        raise PackError("rig manifest is too large or invalid")
    try:
        rig = rig_manifest.validate_manifest(json.loads(raw))
    except (UnicodeError, ValueError, rig_manifest.RigManifestError) as exc:
        raise PackError("rig manifest is invalid") from exc
    if rig["character_id"] != character_id:
        raise PackError("rig manifest character id differs from pack id")
    with tempfile.TemporaryDirectory(prefix=dest.name + ".part.", dir=dest.parent) as stage_name:
        stage = Path(stage_name)
        (stage / "rig.json").write_bytes(raw)
        for asset_id, meta in rig["assets"].items():
            data = download(f"{character_id}/{asset_id}.png")
            if not isinstance(data, bytes) or len(data) > packs.MAX_FILE_BYTES or hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise PackError(f"rig asset {asset_id} does not match its hash or size limit")
            (stage / f"{asset_id}.png").write_bytes(data)
        try:
            rig_manifest.load_manifest(stage / "rig.json", stage)
        except rig_manifest.RigManifestError as exc:
            raise PackError("downloaded rig pack is invalid") from exc
        stage.rename(dest)
    return rig


def storage_downloader(client) -> Callable[[str], bytes]:
    """Adapter for the Supabase storage client (service role); every object lives in the private `story-packs` bucket."""
    return lambda path: client.storage.from_(BUCKET).download(path)
