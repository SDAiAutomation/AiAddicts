"""Rendu de contrôle Manim : une équation et un graphe, avec mesure du temps. Utilisé par le workflow
`growthos-manim-smoke.yml` et utilisable en local : python scripts/manim_smoke.py sortie/"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.motion_graphics import manim_backend, renderer  # noqa: E402

SCENES = {
    "equation": {
        "sceneType": "equation_steps", "title": "Isoler x",
        "steps": [
            {"equation": "3x - 5 = 10", "explanation": "Équation initiale"},
            {"equation": "3x = 15", "explanation": "Ajouter 5 aux deux membres"},
            {"equation": "x = 5", "explanation": "Diviser par 3"},
        ],
        "_reveals": [0.0, 0.30, 0.62], "_duration": 8.0,
    },
    "graphe": {
        "sceneType": "function_graph", "title": "La même réponse en image", "slope": 2, "intercept": 3,
        "xMin": 0, "xMax": 5, "yMin": 0, "yMax": 12, "highlightX": 4,
    },
}


def main(out_dir: str) -> int:
    print(f"manim installé : {manim_backend.manim_installed()} | LaTeX : {manim_backend.latex_available()}")
    if not manim_backend.manim_installed():
        print("Manim n'est pas installé : rien à contrôler")
        return 1
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for name, scene in SCENES.items():
        out = Path(out_dir) / f"{name}.mp4"
        started = time.time()
        # render_clip direct : un repli Pillow silencieux ne doit pas faire croire que Manim marche
        from engine.motion_graphics.theme import resolve_theme
        manim_backend.render_clip(scene, 8.0 if name == "equation" else 6.0, str(out), "1080x1920", 25, resolve_theme(None))
        print(f"{name} : {out.stat().st_size // 1024} Ko en {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "smoke-output"))
