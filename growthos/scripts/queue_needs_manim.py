"""Y a-t-il un épisode de maths en file ? (lecture seule)

Utilisé par le worker GitHub Actions pour n'installer Manim + LaTeX (environ 2 minutes) que lorsqu'un
`content_item` en attente contient une scène `equation_steps` ou `function_graph`. Écrit
`needs_manim=true|false` dans $GITHUB_OUTPUT (ou sur la sortie standard en local). Au moindre doute ou à
la moindre erreur : `false`, donc rendu Pillow comme avant — ce script ne peut jamais bloquer le worker.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MATH_SCENES = {"equation_steps", "function_graph"}


def has_math_scene(script) -> bool:
    blocks = script.get("blocks") if isinstance(script, dict) else None
    return any(
        isinstance(block, dict)
        and isinstance(block.get("motion_graphic"), dict)
        and block["motion_graphic"].get("sceneType") in MATH_SCENES
        for block in (blocks or [])
    )


def queue_needs_manim() -> bool:
    from engine import db

    client = db.get_service_client()
    rows = (
        client.table("content_items").select("script").in_("status", ["queued", "generating"]).limit(200).execute().data
    )
    return any(has_math_scene(row.get("script")) for row in rows or [])


def main() -> int:
    try:
        needed = queue_needs_manim()
    except Exception as exc:  # noqa: BLE001 — jamais bloquant
        print(f"détection impossible ({str(exc)[:160]}) : Pillow", file=sys.stderr)
        needed = False
    line = f"needs_manim={'true' if needed else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
