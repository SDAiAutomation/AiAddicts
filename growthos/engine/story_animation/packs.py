"""Approved asset packs: validation and a synthetic placeholder pack (stdlib only, not wired into the worker).

A pack is a directory of PNG sprites read by the renderer by NAME. Nothing in a story can point the renderer at another
path: the renderer receives one validated directory, and every file it may read is listed below with its exact size.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .renderer import RenderError

# name -> (width, height) of the rig_v1 prototype pack
REQUIRED_SPRITES = {
    "hat": (368, 183), "torso": (248, 350), "glove_l": (250, 253), "glove_r": (250, 253), "shoe_l": (275, 200), "shoe_r": (285, 200),
    "head_neutral": (495, 375), "head_talk": (495, 375), "head_worried": (495, 375), "head_o": (495, 375), "head_blank_pip": (495, 375),
    "clock": (656, 793),
    "ros_head_blank": (700, 552), "ros_head_blank2": (700, 552), "ros_torso": (446, 472),
    "ros_glove_l": (212, 246), "ros_glove_r": (212, 258), "ros_shoe_l": (285, 167), "ros_shoe_r": (290, 167),
    "bg_alley": (1024, 1536), "bg_shop": (1024, 1536), "bg_street": (1024, 1536), "bg_cafe": (1024, 1536),
}
MAX_FILE_BYTES = 12 * 1024 * 1024
_PNG = b"\x89PNG\r\n\x1a\n"


def png_size(path: Path) -> tuple[int, int]:
    """(width, height) read from the PNG header; raises RenderError if the file is not a PNG."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != _PNG or head[12:16] != b"IHDR":
        raise RenderError(f"{path.name} is not a PNG file")
    return struct.unpack(">II", head[16:24])


def validate_pack(pack_dir: Path) -> list[str]:
    """Problems with a pack (empty list = usable). Symbolic links are refused so a pack cannot point outside itself."""
    pack_dir = Path(pack_dir)
    if not pack_dir.is_dir():
        return [f"pack directory {pack_dir.name!r} does not exist"]
    problems = []
    for name, size in REQUIRED_SPRITES.items():
        path = pack_dir / f"{name}.png"
        if path.is_symlink():
            problems.append(f"{name}.png is a symbolic link")
        elif not path.is_file():
            problems.append(f"{name}.png is missing")
        elif path.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{name}.png is larger than {MAX_FILE_BYTES // 1048576} MiB")
        else:
            try:
                got = png_size(path)
            except RenderError as exc:
                problems.append(str(exc))
                continue
            if got != size:
                problems.append(f"{name}.png is {got[0]}x{got[1]}, expected {size[0]}x{size[1]}")
    return problems


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_png(path: Path, width: int, height: int, rgba: tuple[int, int, int, int]) -> None:
    row = b"\x00" + bytes(rgba) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(_PNG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 1)) + _chunk(b"IEND", b""))


def write_placeholder_pack(pack_dir: Path) -> None:
    """Flat-colour sprites with the right sizes: enough to exercise and time the renderer, never to publish."""
    pack_dir = Path(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)
    for i, (name, (w, h)) in enumerate(REQUIRED_SPRITES.items()):
        shade = 40 + (i * 37) % 180
        _write_png(pack_dir / f"{name}.png", w, h, (shade, shade, shade, 255 if name.startswith("bg_") else 230))
