"""Y a-t-il un contenu « Explainer animé » en file ? (lecture seule)

Utilisé par le worker GitHub Actions pour n'installer Chromium (Playwright) et les dépendances de l'Explainer
(`requirements-explainer.txt`) que lorsqu'un `content_item` en attente a `script.visual_style == "explainer"`.
Écrit `needs_explainer=true|false` dans $GITHUB_OUTPUT (ou sur la sortie standard en local). Au moindre doute ou à
la moindre erreur : `false` — ce script ne peut jamais bloquer le worker. Si l'installation manque alors qu'un
contenu Explainer est traité, la génération échoue avec un motif explicite (jamais de repli silencieux).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def is_explainer(script) -> bool:
    return isinstance(script, dict) and str(script.get("visual_style") or "").strip().lower() == "explainer"


def queue_needs_explainer() -> bool:
    """Vrai si au moins un contenu en file (queued / generating) demande l'Explainer. Écrit le décompte au journal : la
    ligne « N contenu(x) en file, M explainer » permet de voir, dans l'étape du worker, ce que la détection a lu."""
    from engine import db

    client = db.get_service_client()
    rows = (
        client.table("content_items").select("script").in_("status", ["queued", "generating"]).limit(200).execute().data
    ) or []
    explainers = sum(1 for row in rows if is_explainer(row.get("script")))
    print(f"{len(rows)} contenu(x) en file, {explainers} explainer")
    return explainers > 0


def main() -> int:
    try:
        needed = queue_needs_explainer()
    except Exception as exc:  # noqa: BLE001 — jamais bloquant
        print(f"détection impossible ({type(exc).__name__}: {str(exc)[:200]}) : installation Explainer selon EXPLAINER_ALWAYS_INSTALL seulement", file=sys.stderr)
        needed = False
    line = f"needs_explainer={'true' if needed else 'false'}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
