"""Cut character 2 (Rosette) and Pip's round-mouth head into rig parts. Native pixels of the 1024x1536 sources."""
import json, os
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "out", "art")
DST = os.path.join(HERE, "..", "sprites")


def load(n):
    return Image.open(os.path.join(SRC, n)).convert("RGBA")


def crop(im, box, name):
    im.crop(box).save(os.path.join(DST, name))


def shift_to(im, ref, y0, y1):
    def c(i):
        ys, xs = np.nonzero(np.asarray(i)[y0:y1, :, 3] > 0)
        return xs.mean(), ys.mean()
    (rx, ry), (x, y) = c(ref), c(im)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (int(round(rx - x)), int(round(ry - y))))
    return out


ros = load("ros_v1_key.png")
crop(ros, (285, 690, 731, 1162), "ros_torso.png")
crop(ros, (88, 872, 300, 1118), "ros_glove_l.png")
crop(ros, (728, 872, 940, 1130), "ros_glove_r.png")
crop(ros, (225, 1235, 510, 1402), "ros_shoe_l.png")
crop(ros, (525, 1235, 815, 1402), "ros_shoe_r.png")
for k, f in {"closed": "ros_v1_key.png", "open": "ros_open_key.png", "o": "ros_o_key.png"}.items():
    crop(shift_to(load(f), ros, 200, 650), (150, 140, 850, 692), f"ros_head_{k}.png")
from PIL import ImageDraw
blank = ros.copy()  # neutral face with the smile painted out: mouths are drawn in code so the face never drifts
ImageDraw.Draw(blank).rectangle((330, 562, 552, 626), fill=(255, 255, 250, 255))
crop(blank, (150, 140, 850, 692), "ros_head_blank.png")
pip = load("pip_v2_key.png")
crop(shift_to(load("pip_o_key.png"), pip, 300, 600), (265, 262, 760, 637), "head_o.png")
print("ok")
