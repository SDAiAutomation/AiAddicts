"""Chroma-key the green backgrounds (local, free) and report connected components."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def key(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    green = (g - np.maximum(r, b)) > 45  # background (flat green, slight gradient)
    alpha = (~green).astype(np.uint8) * 255
    # keep only the largest set of connected non-green pixels' neighbourhood: remove specks, close pinholes
    alpha = ndi.binary_opening(alpha > 0, iterations=1)
    lab, n = ndi.label(alpha)
    sizes = ndi.sum(alpha, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 400])
    keep = ndi.binary_fill_holes(keep) | keep
    rgba = np.dstack([a.clip(0, 255).astype(np.uint8), (keep * 255).astype(np.uint8)])
    # de-spill: pull green out of edge pixels
    edge = ndi.binary_dilation(~keep, iterations=2) & keep
    spill = np.minimum(rgba[..., 1], np.maximum(rgba[..., 0], rgba[..., 2]) + 10)
    rgba[..., 1] = np.where(edge, spill, rgba[..., 1])
    return Image.fromarray(rgba, "RGBA")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        im = key(p)
        out = p.replace(".png", "_key.png")
        im.save(out)
        al = np.asarray(im)[..., 3] > 0
        lab, n = ndi.label(al)
        print(out, "components:", n)
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            h = sl[0].stop - sl[0].start; w = sl[1].stop - sl[1].start
            if h * w > 4000:
                print("  comp", i, "x", sl[1].start, sl[1].stop, "y", sl[0].start, sl[0].stop)
