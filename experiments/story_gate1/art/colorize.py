"""Build the colour pack ("couleur_v1") from the prototype sprites.

Characters are recoloured deterministically so the rig keeps working: every sprite keeps its exact size, alpha and ink lines.
 - skin, gloves, faces: the white paper is multiplied by a warm tone (black ink stays black);
 - flat black clothes (suit, dress, hat, shoes): the black fill becomes a colour with a lighter cel band and a darker edge,
   everything that is not black (bow tie, collar) is kept;
 - backgrounds and the alarm clock come from OpenAI image edits (recolor.py), copied in as they are.

usage: colorize.py OPENAI_DIR OUT_DIR"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "sprites")

SKIN = (1.0, 0.86, 0.72)
GLOVE = (1.0, 0.95, 0.84)
FLAT = {  # name -> (fill, edge)
    "hat": ((120, 78, 44), (46, 28, 14)),
    "torso": ((24, 112, 124), (8, 44, 52)),
    "shoe_l": ((112, 36, 36), (44, 12, 12)),
    "shoe_r": ((112, 36, 36), (44, 12, 12)),
    "ros_torso": ((104, 52, 128), (38, 16, 52)),
    "ros_shoe_l": ((72, 48, 72), (26, 16, 26)),
    "ros_shoe_r": ((72, 48, 72), (26, 16, 26)),
}
MULTIPLY = {
    "head_neutral": SKIN, "head_talk": SKIN, "head_worried": SKIN, "head_o": SKIN, "head_blank_pip": SKIN,
    "ros_head_blank": SKIN, "ros_head_blank2": SKIN,
    "glove_l": GLOVE, "glove_r": GLOVE, "ros_glove_l": GLOVE, "ros_glove_r": GLOVE,
}
OPENAI = ("bg_shop", "bg_alley", "bg_cafe", "bg_street", "clock")


def multiply(im: Image.Image, tone) -> Image.Image:
    a = np.asarray(im).astype(np.float32)
    a[..., 0] *= tone[0]
    a[..., 1] *= tone[1]
    a[..., 2] *= tone[2]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def flat_fill(im: Image.Image, fill, edge) -> Image.Image:
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    alpha = a[..., 3] / 255.0
    black = (a[..., :3].max(axis=2) < 70) & (alpha > 0.5)
    mask = Image.fromarray((alpha * 255).astype(np.uint8), "L")
    inner = np.asarray(mask.filter(ImageFilter.MinFilter(9))).astype(np.float32) / 255.0   # erode: what is left is the body
    ring = np.clip(alpha - inner, 0, 1)                                                   # the outer rim
    xs = np.linspace(0, 1, w)[None, :].repeat(h, axis=0)
    band = np.clip(1.0 - np.abs(xs - 0.28) / 0.22, 0, 1) * 0.22                           # a lighter cel band on the lit side
    base = np.array(fill, np.float32)[None, None, :]
    shaded = base * (1.0 + band[..., None])
    rim = np.array(edge, np.float32)[None, None, :]
    painted = shaded * (1 - ring[..., None]) + rim * ring[..., None]
    out = a.copy()
    out[..., :3] = np.where(black[..., None], painted, a[..., :3])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main(openai_dir: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "growthos"))
    from engine.story_animation.packs import REQUIRED_SPRITES  # the pack is exactly these 23 names

    for name in sorted(REQUIRED_SPRITES):
        fn = name + ".png"
        if name in OPENAI:
            im = Image.open(os.path.join(openai_dir, fn)).convert("RGBA")
        else:
            src = Image.open(os.path.join(SRC, fn)).convert("RGBA")
            if name in FLAT:
                im = flat_fill(src, *FLAT[name])
            elif name in MULTIPLY:
                im = multiply(src, MULTIPLY[name])
            else:
                raise SystemExit(f"no recipe for {name}")
        ref = Image.open(os.path.join(SRC, fn))
        assert im.size == ref.size, (name, im.size, ref.size)
        im.save(os.path.join(out_dir, fn))
        print("ok", name)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
