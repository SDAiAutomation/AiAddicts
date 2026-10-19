"""Compare low/medium sur le même storyboard Explainer avec rendus synthétiques.

Sans --execute, affiche seulement le budget logiciel estimé et ne fait aucun appel API.
L'exécution utilise Anthropic et Chromium ; la narration est fixe, les timings sont estimés
et les vidéos ne sont PAS synchronisées sur une vraie voix. Ne pas publier ces aperçus.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOPIC = "Pourquoi le ciel est bleu ?"
LINES = [
    "Pourquoi le ciel paraît-il bleu pendant la journée ?",
    "La lumière du Soleil contient plusieurs couleurs.",
    "Les molécules de l'air diffusent davantage la lumière bleue que la lumière rouge.",
    "Cette lumière bleue nous arrive alors de nombreuses directions.",
    "Au coucher du Soleil, son trajet dans l'atmosphère s'allonge et les teintes rouges dominent.",
]


def composer_cost(report: dict) -> float | None:
    calls = [c for c in report["spend"]["calls"] if c["step"].startswith("composer")]
    costs = [c.get("costUsd") for c in calls]
    return round(sum(costs), 5) if costs and all(cost is not None for cost in costs) else None


def run_sweep(out: Path, budget: float) -> list[dict]:
    from engine.explainer import director, llm, pipeline

    if not __import__("os").environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY manquante")
    original_complete = llm.complete
    original_direct = director.direct
    shared_storyboard = None
    rows = []
    for effort in ("low", "medium"):
        def complete_with_effort(spend, step, model, system, user, max_tokens=16000, effort="medium"):
            return original_complete(spend, step, model, system, user, max_tokens=max_tokens,
                                     effort=selected if step.startswith("composer") else effort)

        selected = effort
        def direct_once(*args, **kwargs):
            return original_direct(*args, **kwargs) if shared_storyboard is None else {"storyboard": shared_storyboard, "attempts": 0}

        with patch.object(llm, "complete", side_effect=complete_with_effort), patch.object(director, "direct", side_effect=direct_once):
            report = pipeline.generate(TOPIC, out / effort, lines=list(LINES), mode="templates", use_critic=False,
                                       budget_usd=budget, do_render=True)
        if shared_storyboard is None:
            shared_storyboard = report["storyboard"]
        rows.append({"effort": effort, "composerCostUsd": composer_cost(report),
                     "totalCostUsd": None if report["spend"]["unknownCost"] else report["spend"]["totalUsd"],
                     "fallbackPlans": [f["plan"] for f in report["fallbacks"]], "fallbacks": len(report["fallbacks"]),
                     "video": report.get("video"), "timingSource": "estimated", "voiceSynchronized": False})
    return rows


def comparison(rows: list[dict]) -> str:
    def fmt(value):
        return "n/d" if value is None else str(value)
    lines = ["| effort compositeur | coût compositeur estimé ($) | coût total estimé ($) | plans en repli | vidéo |",
             "|---|---:|---:|---|---|"]
    for row in rows:
        lines.append(f"| {row['effort']} | {fmt(row['composerCostUsd'])} | {fmt(row['totalCostUsd'])} | "
                     f"{', '.join(row['fallbackPlans']) or 'aucun'} | {fmt(row['video'])} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="autorise les appels Anthropic et les deux rendus")
    parser.add_argument("--out", type=Path, default=Path("explainer-effort-sweep"))
    parser.add_argument("--budget-usd", type=float, default=1.20, help="budget logiciel par rendu (non garanti comme plafond de facturation)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.budget_usd) or args.budget_usd <= 0:
        parser.error("--budget-usd doit être un nombre positif et fini")
    print(f"Budget logiciel estimé : 2 × {args.budget_usd:.2f} $ = {2 * args.budget_usd:.2f} $ ; "
          "la facture réelle peut dépasser ce budget si le dernier appel dépasse sa réserve.")
    if not args.execute:
        print("Aucun appel effectué. --execute déclenche des appels Anthropic payants et deux rendus Chromium.")
        return 0
    rows = run_sweep(args.out, args.budget_usd)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "comparison.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(comparison(rows))
    print("Aperçus synthétiques : timings estimés, sans voix réelle synchronisée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
