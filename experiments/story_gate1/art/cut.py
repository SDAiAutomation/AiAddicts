"""Cut the keyed character into rig parts (local, free). Coordinates are native pixels of pip_v2 (1024x1536)."""
import json, os
import numpy as np
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", "art")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sprites")
os.makedirs(DST, exist_ok=True)


def load(name):
    return Image.open(os.path.join(SRC, name)).convert("RGBA")


def crop(im, box, name):
    c = im.crop(box)
    c.save(os.path.join(DST, name))
    return {"file": name, "x": box[0], "y": box[1], "w": box[2] - box[0], "h": box[3] - box[1]}


def head_shift(im, ref):
    """integer (dx, dy) that aligns the alpha centroid of the face zone (y 300-600) of im onto ref."""
    def c(i):
        a = np.asarray(i)[300:600, :, 3] > 0
        ys, xs = np.nonzero(a)
        return xs.mean(), ys.mean()
    (rx, ry), (x, y) = c(ref), c(im)
    return int(round(rx - x)), int(round(ry - y))


base = load("pip_v2_key.png")
meta = {}
meta["hat"] = crop(base, (335, 55, 703, 238), "hat.png")
meta["torso"] = crop(base, (385, 636, 633, 986), "torso.png")
meta["glove_l"] = crop(base, (75, 862, 325, 1115), "glove_l.png")
meta["glove_r"] = crop(base, (700, 862, 950, 1115), "glove_r.png")
meta["shoe_l"] = crop(base, (235, 1232, 510, 1432), "shoe_l.png")
meta["shoe_r"] = crop(base, (510, 1232, 795, 1432), "shoe_r.png")
HEAD = (265, 262, 760, 637)
for key, f in {"neutral": "pip_v2_key.png", "talk": "pip_talk_key.png", "worried": "pip_worried2_key.png"}.items():
    im = load(f)
    dx, dy = head_shift(im, base)
    shifted = Image.new("RGBA", im.size, (0, 0, 0, 0))
    shifted.paste(im, (dx, dy))
    meta["head_" + key] = crop(shifted, HEAD, f"head_{key}.png")
clock = load("clock_key.png")
meta["clock"] = crop(clock, (190, 365, 846, 1158), "clock.png")
bg = Image.open(os.path.join(SRC, "bg_alley.png")).convert("RGB").resize((640, 960), Image.LANCZOS)
bg.save(os.path.join(DST, "bg_alley.png"))
meta["bg"] = {"file": "bg_alley.png", "w": 640, "h": 960}
json.dump(meta, open(os.path.join(DST, "parts.json"), "w"), indent=1)
print({k: (v["w"], v["h"]) for k, v in meta.items()})
