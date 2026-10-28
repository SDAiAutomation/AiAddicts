"""Y a-t-il une histoire animée à traiter en file ? (lecture seule)

Premier job léger du workflow `story-animation-worker.yml` : le job lourd (Godot, packs, rendu) ne démarre que si
`has_work=true`. Reconnaît une histoire animée avec `engine.story_animation.contract.is_animated` (même règle que
`claim.py`). Compte les items animés `queued`, ainsi que ceux restés `generating` au-delà du seuil de
`repo.reclaim_stale_generating_items` (un job lourd tué les laisse orphelins ; `claim_animated_item` les remettrait en
file, encore faut-il démarrer). Écrit `has_work=true|false` dans $GITHUB_OUTPUT (ou sur la sortie standard en local).

Erreurs :
- configuration (variables Supabase absentes, client impossible à créer) : `has_work=false` ET code de sortie 1, pour que
  le job soit rouge et qu'une panne de configuration ne passe pas pour une file vide ;
- erreur transitoire de requête : `has_work=false`, code 0, log + `::warning::` GitHub ; le prochain réveil reprendra.
Aucune écriture, aucun appel payant.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import repo  # noqa: E402
from engine.story_animation import contract  # noqa: E402

WINDOW = 200  # même fenêtre que claim.py


def _is_stale(updated_at, now: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
    except ValueError:
        return True  # horodatage illisible : mieux vaut démarrer que laisser un item orphelin
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < now - timedelta(minutes=repo._STALE_GENERATING_MINUTES)


def queue_has_animated(client, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    rows = (
        client.table("content_items")
        .select("id, script, status, updated_at")
        .in_("status", ["queued", "generating"])
        .order("created_at")
        .limit(WINDOW)
        .execute()
        .data
    ) or []
    animated = 0
    for row in rows:
        if not contract.is_animated(row.get("script")):
            continue
        if row.get("status") == "queued" or _is_stale(row.get("updated_at"), now):
            animated += 1
    print(f"{len(rows)} contenu(x) queued/generating, {animated} histoire(s) animée(s) à traiter")
    return animated > 0


def _emit(needed: bool) -> None:
    line = f"has_work={'true' if needed else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main() -> int:
    try:
        from engine import db

        client = db.get_service_client()
    except Exception as exc:  # noqa: BLE001 — configuration : on échoue en rouge
        print(f"::error::configuration Supabase invalide ({type(exc).__name__}: {str(exc)[:200]})", file=sys.stderr)
        _emit(False)
        return 1
    try:
        needed = queue_has_animated(client)
    except Exception as exc:  # noqa: BLE001 — transitoire : non bloquant
        print(f"::warning::détection impossible ({type(exc).__name__}: {str(exc)[:200]}) : has_work=false", file=sys.stderr)
        needed = False
    _emit(needed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
