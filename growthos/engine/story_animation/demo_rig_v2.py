"""Draw original, offline cutout fixtures and a three-character scene. No provider calls or licensed packs.

Requires Pillow only for this developer benchmark; the renderer itself does not.
Run: python -m growthos.engine.story_animation.demo_rig_v2 --out <directory>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from . import rig_manifest, rig_v2


def _png(path: Path, size: tuple[int, int], shape: str, fill: str, accent: str) -> None:
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    w, h = size
    border = (35, 30, 36, 255)
    if shape == "owl_head":
        draw.ellipse((4, 3, w - 4, h - 4), fill=fill, outline=border, width=7)
        draw.polygon([(w * 0.41, h * 0.72), (w * 0.59, h * 0.72), (w * 0.5, h * 0.88)], fill=accent, outline=border)
        draw.polygon([(20, 38), (35, 1), (90, 27)], fill=fill, outline=border)
        draw.polygon([(w - 20, 38), (w - 35, 1), (w - 90, 27)], fill=fill, outline=border)
    elif shape == "wing":
        draw.ellipse((3, 10, w - 3, h - 10), fill=fill, outline=border, width=6)
        for i in range(1, 5):
            x = i * w / 5
            draw.line((x, h * 0.55, x + 18, h * 0.84), fill=accent, width=4)
    elif shape == "torso":
        draw.rounded_rectangle((5, 4, w - 5, h - 4), radius=min(w, h) // 3, fill=fill, outline=border, width=7)
        draw.ellipse((w * 0.22, h * 0.18, w * 0.78, h * 0.72), fill=accent)
    elif shape == "shoe":
        draw.ellipse((2, h * 0.24, w - 2, h - 2), fill=fill, outline=border, width=6)
    elif shape == "hand":
        draw.ellipse((3, 3, w - 3, h - 3), fill=fill, outline=border, width=5)
    else:
        draw.ellipse((4, 4, w - 4, h - 4), fill=fill, outline=border, width=7)
        if shape == "rosette_head":
            draw.arc((15, 5, w - 15, h * 0.75), 180, 350, fill=accent, width=14)
        elif shape == "pip_head":
            draw.rounded_rectangle((w * 0.14, h * 0.08, w * 0.86, h * 0.24), radius=15, fill=accent, outline=border, width=4)
    im.save(path)


CAST = {
    "pip": {
        "canvas": [700, 900], "anchors": {"hip": [350, 520], "neck": [350, 285], "shoulder_l": [275, 330], "shoulder_r": [425, 330], "hip_l": [315, 520], "hip_r": [385, 520], "wrist_l": [190, 500], "wrist_r": [510, 500], "ankle_l": [310, 805], "ankle_r": [390, 805]},
        "face": {"eye_l": [76, 105], "eye_r": [154, 105], "mouth": [115, 175]},
        "parts": {"torso": ((190, 300), "torso"), "head": ((230, 230), "pip_head"), "hand_l": ((72, 75), "hand"), "hand_r": ((72, 75), "hand"), "foot_l": ((110, 70), "shoe"), "foot_r": ((110, 70), "shoe")},
        "colors": ("#438aa6", "#f0cfaa", "#f0cfaa", "#283c55"),
    },
    "rosette": {
        "canvas": [700, 900], "anchors": {"hip": [350, 570], "neck": [350, 310], "shoulder_l": [215, 380], "shoulder_r": [485, 380], "hip_l": [300, 570], "hip_r": [400, 570], "wrist_l": [120, 570], "wrist_r": [580, 570], "ankle_l": [310, 800], "ankle_r": [390, 800]},
        "face": {"eye_l": [95, 105], "eye_r": [205, 105], "mouth": [150, 180]},
        "parts": {"torso": ((335, 330), "torso"), "head": ((300, 245), "rosette_head"), "hand_l": ((85, 90), "hand"), "hand_r": ((85, 90), "hand"), "foot_l": ((125, 70), "shoe"), "foot_r": ((125, 70), "shoe")},
        "colors": ("#b96171", "#ecc99d", "#ecc99d", "#512f49"),
    },
    "tavi_owl": {
        "canvas": [700, 700], "anchors": {"hip": [350, 450], "neck": [350, 310], "shoulder_l": [290, 350], "shoulder_r": [410, 350], "hip_l": [320, 450], "hip_r": [380, 450], "wrist_l": [100, 390], "wrist_r": [600, 390], "ankle_l": [320, 590], "ankle_r": [380, 590]},
        "face": {"eye_l": [91, 83], "eye_r": [189, 83], "mouth": [140, 139]},
        "parts": {"torso": ((270, 260), "torso"), "head": ((280, 205), "owl_head"), "hand_l": ((255, 95), "wing"), "hand_r": ((255, 95), "wing"), "foot_l": ((85, 60), "shoe"), "foot_r": ((85, 60), "shoe")},
        "colors": ("#80624a", "#b9956a", "#9b7858", "#e6be6a"),
    },
}


def create(out: Path, frames_per_shot: int = 96) -> tuple[Path, Path]:
    out = Path(out)
    pack = out / "pack"
    for character_id, spec in CAST.items():
        home = pack / character_id
        home.mkdir(parents=True, exist_ok=True)
        assets = {}
        for role, (size, shape) in spec["parts"].items():
            color = spec["colors"][1 if role == "head" else 2 if role.startswith("hand") else 3 if role.startswith("foot") else 0]
            path = home / f"{role}.png"
            _png(path, size, shape, color, spec["colors"][3])
            assets[role] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "width": size[0], "height": size[1]}
        manifest = {
            "schema_version": 1, "character_id": character_id, "rig_type": "cutout_2d",
            "canvas": spec["canvas"], "anchors": spec["anchors"], "face": spec["face"],
            "sprites": {role: role for role in spec["parts"]}, "assets": assets,
            "expressions": sorted(rig_manifest.EXPRESSIONS),
            "actions": sorted(rig_manifest.ACTIONS), "mouths": ["closed", "open", "round"],
        }
        rig_manifest.validate_manifest(manifest)
        (home / "rig.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    def actor(who: str, x: float, action: str, expression: str, speaking: bool = False) -> dict:
        track = ("ccoorr" * (frames_per_shot // 6 + 1))[:frames_per_shot] if speaking else "c" * frames_per_shot
        return {"character_id": who, "x": x, "facing": "right" if x < 0.5 else "left", "action": action, "expression": expression, "mouth_track": track}
    shots = [
        {"setting": "forest", "camera": {"move": "static", "zoom_from": 0.9, "zoom_to": 0.9}, "transition": "cut", "subtitle": "Trois silhouettes, un même moteur", "actors": [actor("pip", 0.23, "idle", "neutral"), actor("tavi_owl", 0.5, "react", "surprised"), actor("rosette", 0.77, "idle", "neutral")]},
        {"setting": "forest", "camera": {"move": "push_in", "zoom_from": 1.0, "zoom_to": 1.2}, "transition": "cut", "subtitle": "Tavi découvre la forêt qui disparaît.", "actors": [actor("pip", 0.27, "talk", "sad", True), actor("tavi_owl", 0.72, "point", "surprised")]},
        {"setting": "forest", "camera": {"move": "pan_right", "zoom_from": 1.0, "zoom_to": 1.0}, "transition": "fade", "subtitle": "Ensemble, ils cherchent la cause.", "actors": [actor("tavi_owl", 0.32, "walk", "happy", True), actor("rosette", 0.75, "react", "happy")]},
    ]
    for i, shot in enumerate(shots):
        shot["start_frame"] = i * frames_per_shot
        shot["end_frame"] = (i + 1) * frames_per_shot
    timeline = {"rig_schema_version": 1, "fps": rig_v2.FPS, "total_frames": len(shots) * frames_per_shot, "characters": list(CAST), "shots": shots}
    rig_v2.validate_timeline(timeline, pack)
    path = out / "demo_timeline.json"
    path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, pack


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--frames-per-shot", type=int, default=96)
    args = parser.parse_args()
    timeline_file, pack_dir = create(args.out, args.frames_per_shot)
    print(json.dumps({"timeline": str(timeline_file), "pack": str(pack_dir)}))
