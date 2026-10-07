"""Contrôle automatique d'un clip de maths : l'écran de calcul ne se vide jamais le temps d'une transition.

Un fondu enchaîné laisse des glyphes fantômes ; un fondu séquentiel peut laisser une ligne
d'équation vide (seul le signe « = ») pendant quelques images. Ce script mesure, image par image,
la quantité d'« encre » dans la bande de la ligne d'équation (30 %-44 % de la hauteur, hors colonne
centrale où se trouve le « = ») et signale les creux : une image dont l'encre tombe sous `--ratio`
de celle des images voisines. Calibrage (pire rapport mesuré sur la même scène) : fondu séquentiel
0,000 (7 images vides) ; recouvrement de 25 % 0,096 ; croisement linéaire à 50 % 0,185 (le minimum
vient du texte vert pâle, moins contrasté que le blanc voisin) ; seuil par défaut 0,15.

    python scripts/check_clip_continuity.py output/.../images/motion-02.mp4
    python scripts/check_clip_continuity.py clip.mp4 --ratio 0.15 --window 6

Mesure objective, mais limitée : elle ne remplace pas un visionnage (elle ne juge ni la lisibilité,
ni la justesse de la synchronisation).
"""
from __future__ import annotations

import argparse
import subprocess
import sys

W, H = 270, 76  # bande de la ligne d'équation, sous-échantillonnée
BAND_TOP, BAND_HEIGHT = 0.30, 0.14
EQUALS_COLUMNS = (int(W * 0.44), int(W * 0.56))  # le signe « = » est fixe : on ne le compte pas


def ink_per_frame(path: str, fps: int = 25) -> list[float]:
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-vf", f"fps={fps},crop=iw:ih*{BAND_HEIGHT}:0:ih*{BAND_TOP},scale={W}:{H},format=gray",
        "-f", "rawvideo", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    size = W * H
    frames = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    values = []
    lo, hi = EQUALS_COLUMNS
    for frame in frames:
        counts = [0] * 256
        for pixel in frame:
            counts[pixel] += 1
        background = max(range(256), key=counts.__getitem__)  # le fond est la valeur dominante
        # Masse d'encre (somme des écarts au fond), pas un compte de pixels au-dessus d'un seuil : un
        # trait fin et pâle réduit à l'échelle passerait sous le seuil alors qu'il reste lisible.
        mass = sum(abs(pixel - background) for index, pixel in enumerate(frame) if not lo <= index % W < hi)
        values.append(mass / (255 * size))
    return values


def dips(ink: list[float], ratio: float = 0.15, window: int = 6, floor: float = 0.002) -> list[tuple[int, float, float]]:
    """(image, encre, encre de référence voisine) pour chaque creux entouré de contenu des deux côtés."""
    found = []
    for i, value in enumerate(ink):
        before = ink[max(0, i - window):i]
        after = ink[i + 1:i + 1 + window]
        if not before or not after:
            continue
        reference = min(max(before), max(after))
        if reference >= floor and value < reference * ratio:
            found.append((i, value, reference))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("clip")
    parser.add_argument("--ratio", type=float, default=0.15, help="creux = encre < ratio x encre voisine (défaut 0.15)")
    parser.add_argument("--window", type=int, default=6, help="images voisines comparées de chaque côté")
    parser.add_argument("--fps", type=int, default=25)
    args = parser.parse_args()
    ink = ink_per_frame(args.clip, args.fps)
    if not ink:
        print("aucune image lue")
        return 2
    found = dips(ink, args.ratio, args.window)
    print(f"{len(ink)} images, encre moyenne {sum(ink) / len(ink):.3f}, {len(found)} creux")
    for index, value, reference in found[:12]:
        print(f"  creux à {index / args.fps:5.2f} s : encre {value:.3f} pour {reference:.3f} autour")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
