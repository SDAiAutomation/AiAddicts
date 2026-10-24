"""Remove leftover green-screen spill from every cut sprite (local, free): clamp green to the max of red/blue where it dominates."""
import glob, os
import numpy as np
from PIL import Image

for p in glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sprites", "*.png")):
    if os.path.basename(p).startswith("bg_"):
        continue
    a = np.asarray(Image.open(p).convert("RGBA")).copy()
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    m = (a[..., 3] > 0) & (g > np.maximum(r, b) + 12)
    a[..., 1] = np.where(m, np.maximum(r, b), a[..., 1])
    Image.fromarray(a, "RGBA").save(p)
    print(os.path.basename(p), int(m.sum()))
