"""Y a-t-il une histoire animée « queued » en file ? (lecture seule)

Premier job léger du workflow `story-animation-worker.yml` : le job lourd (Godot, packs, rendu) ne démarre que si
`has_work=true`. Reconnaît une histoire animée avec `engine.story_animation.contract.is_animated` (même règle que
`claim.py`). Écrit `has_work=true|false` dans $GITHUB_OUTPUT (ou sur la sortie standard en local). Au moindre doute ou
à la moindre erreur : `false`, code de sortie 0 — le prochain réveil planifié ou le dispatch du site reprendra.
Aucune écriture, aucun appel payant.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WINDOW = 200  # même fenêtre que claim.py


def queue_has_animated(client) -> bool:
    from engine.story_animation import contract

    rows = (
        client.table("content_items").select("id, script").eq("status", "queued").order("created_at").limit(WINDOW).execute().data
    ) or []
    animated = sum(1 for row in rows if contract.is_animated(row.get("script")))
    print(f"{len(rows)} contenu(x) queued, {animated} histoire(s) animée(s)")
    return animated > 0


def main() -> int:
    try:
        from engine import db

        needed = queue_has_animated(db.get_service_client())
    except Exception as exc:  # noqa: BLE001 — jamais bloquant
        print(f"détection impossible ({type(exc).__name__}: {str(exc)[:200]}) : has_work=false", file=sys.stderr)
        needed = False
    line = f"has_work={'true' if needed else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
