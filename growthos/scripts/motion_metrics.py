"""Mesures de mouvement d'une video rendue, par le code (pas de LLM) : reproductibles et gratuites.
Usage : python scripts/motion_metrics.py video_ou_url [...]   (sortie JSON, une ligne par video).
Echelle : image 108x192 niveaux de gris a 10 i/s ; difference moyenne absolue entre images consecutives (0-255)."""
import json, subprocess, sys

import numpy as np

W, H, FPS = 108, 192, 10
STATIC = 0.15   # en dessous : image considérée figée (bruit d'encodage inclus)
CUT = 12.0      # au-dessus : changement brutal (coupe / nouvelle mise en page)


def frames(src: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", f"fps={FPS},scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    return a[: a.size // (W * H) * W * H].reshape(-1, H, W).astype(np.int16)


def longest_run(mask: np.ndarray) -> int:
    best = run = 0
    for m in mask:
        run = run + 1 if m else 0
        best = max(best, run)
    return best


def metrics(src: str) -> dict | None:
    f = frames(src)
    if len(f) < FPS * 3:
        return None
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    dur = len(f) / FPS
    return {
        "duration_s": round(dur, 1),
        "activity": round(float(d.mean()), 3),
        "static_ratio": round(float((d < STATIC).mean()), 3),
        "max_static_s": round(longest_run(d < STATIC) / FPS, 1),
        "cuts_per_10s": round(float((d > CUT).sum()) / dur * 10, 2),
        "hook_activity_3s": round(float(d[: FPS * 3].mean()), 3),
    }


if __name__ == "__main__":
    for s in sys.argv[1:]:
        print(json.dumps({"src": s, **(metrics(s) or {"error": "trop court"})}, ensure_ascii=False))
