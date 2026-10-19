"""Mesures réelles de l'Explainer, relevées sur les vidéos déjà générées (lecture seule).

    python scripts/explainer_measures.py [--limit 20] [--json]

Lit `content_items.generation_cost_report.explainer` des contenus `visual_style = "explainer"` et affiche, par vidéo puis en
moyenne : coût LLM estimé, mode, plans, replis, durée de rendu Chromium, durée totale, source des timings, bruitages.
Une valeur absente s'affiche « n/d » : jamais zéro. Le surcoût d'installation de Chromium n'est PAS dans la base : il est
dans le journal du worker (étape « Installer Chromium et les dépendances Explainer », ligne « Installation Explainer : N s »).
La moyenne n'est qu'un ordre de grandeur tant que l'échantillon est petit : le nombre de vidéos est affiché.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def explainer_row(item: dict) -> dict | None:
    """Une ligne de mesure à partir d'un content_item, ou None s'il n'a pas de bloc `explainer` au rapport de coût."""
    report = item.get("generation_cost_report")
    block = report.get("explainer") if isinstance(report, dict) else None
    if not isinstance(block, dict):
        return None
    return {
        "id": item.get("id"), "title": item.get("title"), "updatedAt": item.get("updated_at"),
        "mode": block.get("mode"), "plans": block.get("plans"), "fallbacks": block.get("fallbacks"),
        "llmCostUsd": block.get("cost") if not block.get("costUnknown") else None,
        "inputTokens": block.get("inputTokens"), "outputTokens": block.get("outputTokens"),
        "cacheReadTokens": block.get("cacheReadTokens"), "cacheWriteTokens": block.get("cacheWriteTokens"),
        "cacheReadRate": block.get("cacheReadRate"), "costByStepUsd": block.get("costByStepUsd"),
        "renderSeconds": block.get("renderSeconds"), "totalSeconds": block.get("totalSeconds"),
        "timingSource": block.get("timingSource"), "sfxIncluded": block.get("sfxIncluded"), "reused": block.get("reused"),
        "totalEstimatedCost": report.get("totalEstimatedCost"), "missingRates": report.get("missingRates") or [],
    }


def _mean(values: list) -> float | None:
    numbers = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return round(sum(numbers) / len(numbers), 3) if numbers else None


def summarize(rows: list[dict]) -> dict:
    """Moyennes sur les vidéos qui ont la valeur (les rendus réutilisés sans appel LLM sont exclus du coût et du rendu)."""
    fresh = [r for r in rows if not r.get("reused")]
    return {
        "videos": len(rows), "freshRenders": len(fresh),
        "meanLlmCostUsd": _mean([r["llmCostUsd"] for r in fresh]),
        "meanRenderSeconds": _mean([r["renderSeconds"] for r in fresh]),
        "meanTotalSeconds": _mean([r["totalSeconds"] for r in fresh]),
        "meanFallbacks": _mean([r["fallbacks"] for r in fresh]),
        "estimatedTimings": sum(1 for r in rows if r.get("timingSource") != "measured"),
    }


def fmt(value, suffix: str = "") -> str:
    return "n/d" if value is None else f"{value}{suffix}"


def render_table(rows: list[dict]) -> str:
    lines = ["| vidéo | mode | plans | replis | LLM ($) | rendu (s) | total (s) | timings | bruitages |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {str(r['id'])[:8]} | {fmt(r['mode'])} | {fmt(r['plans'])} | {fmt(r['fallbacks'])} | {fmt(r['llmCostUsd'])} | "
                     f"{fmt(r['renderSeconds'])} | {fmt(r['totalSeconds'])} | {fmt(r['timingSource'])} | {fmt(r['sfxIncluded'])} |")
    lines += ["", "| vidéo | entrée | sortie | cache lu | cache écrit | taux cache | coût par étape ($) |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        steps = r["costByStepUsd"]
        step_text = ", ".join(f"{key}: {fmt(value)}" for key, value in sorted(steps.items())) if isinstance(steps, dict) and steps else "n/d"
        rate = r["cacheReadRate"]
        lines.append(f"| {str(r['id'])[:8]} | {fmt(r['inputTokens'])} | {fmt(r['outputTokens'])} | "
                     f"{fmt(r['cacheReadTokens'])} | {fmt(r['cacheWriteTokens'])} | "
                     f"{fmt(f'{rate:.1%}' if rate is not None else None)} | {step_text} |")
    s = summarize(rows)
    lines += ["", f"{s['videos']} vidéo(s), dont {s['freshRenders']} rendu(s) neuf(s) ; moyennes sur les rendus neufs : "
                  f"LLM {fmt(s['meanLlmCostUsd'], ' $')}, rendu {fmt(s['meanRenderSeconds'], ' s')}, total {fmt(s['meanTotalSeconds'], ' s')}, "
                  f"replis {fmt(s['meanFallbacks'])}.",
              f"Timings estimés (à investiguer, attendu : 0) : {s['estimatedTimings']}."]
    return "\n".join(lines)


def fetch(limit: int) -> list[dict]:
    from engine import db

    client = db.get_service_client()
    items = (client.table("content_items").select("id, title, updated_at, generation_cost_report")
             .eq("script->>visual_style", "explainer").not_.is_("generation_cost_report", "null")
             .order("updated_at", desc=True).limit(limit).execute().data)
    return [row for row in (explainer_row(i) for i in items or []) if row]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="sortie JSON au lieu du tableau")
    args = parser.parse_args()
    rows = fetch(args.limit)
    if not rows:
        print("Aucune vidéo explainer avec rapport de coût pour l'instant.")
        return 0
    print(json.dumps({"rows": rows, "summary": summarize(rows)}, ensure_ascii=False, indent=1) if args.json else render_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
