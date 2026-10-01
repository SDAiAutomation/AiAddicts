"""Benchmark Retention Engine V1 : PocketLogic + comparaison avant/après.

Aucun appel externe : analyse déterministe de scripts déjà écrits
(`engine/retention.py`). Rien n'est rendu ni publié.

    python scripts/retention_benchmark.py            # écrit content/scripts/retention/BENCHMARK.md
    python scripts/retention_benchmark.py --print    # affiche seulement

Les scripts « après » sont réécrits À LA MAIN selon l'architecture
STOP/HOLD/PROGRESS/REWARD/RETURN : ce ne sont PAS des sorties du LLM, donc le
rapport décrit des différences de STRUCTURE, pas la performance du prompt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import retention, script as script_module  # noqa: E402

SCRIPTS = ROOT / "content" / "scripts"
REPORT_PATH = SCRIPTS / "retention" / "BENCHMARK.md"
POCKETLOGIC = sorted((SCRIPTS / "pocketlogic").glob("*.json"))
# (nom, script actuel du benchmark Phase 2, version Retention Engine écrite à la main)
BEFORE_AFTER = [
    ("Finance (Motion Graphics)", SCRIPTS / "benchmark" / "b-finance.motion_graphics.json",
     SCRIPTS / "retention" / "after" / "b-finance.after.json"),
    ("Storytelling (images IA)", SCRIPTS / "benchmark" / "a-storytelling.base.json",
     SCRIPTS / "retention" / "after" / "a-storytelling.after.json"),
    ("Explainer (stock footage)", SCRIPTS / "benchmark" / "c-explainer.stock_footage.json",
     SCRIPTS / "retention" / "after" / "c-explainer.after.json"),
]


def load(path: Path) -> dict:
    data = script_module.normalize_script(json.loads(path.read_text(encoding="utf-8")))
    script_module.validate_script(data)
    return data


def _scene(block: dict) -> str:
    mg = block.get("motion_graphic")
    return (mg or {}).get("sceneType") or block.get("shotType") or "-"


def concept_section(path: Path) -> str:
    data = load(path)
    report = retention.analyze(data)
    cs = data["contentStrategy"]
    lines = [f"### {data['title']}", ""]
    lines += [
        f"- **audiencePromise** : {cs['audiencePromise']}",
        f"- **hookType** : `{cs['hookType']}` — « {cs['hookText']} »",
        f"- **coreQuestion** : {cs['coreQuestion']}",
        f"- **payoff** : {cs['payoff']}",
        f"- **CTA** ({cs['ctaIntent']}) : « {report['cta']['text']} »",
    ]
    for loop in report["openLoops"]:
        lines.append(
            f"- **open loop** : « {loop['question']} » ouverte au bloc {loop['openedAtBlock'] + 1}, "
            f"résolue au bloc {loop['resolvedAtBlock'] + 1 if loop['resolvedAtBlock'] is not None else '—'} "
            f"({loop.get('status')}, {loop.get('delaySec', '?')} s)"
        )
    if data.get("series"):
        s = data["series"]
        lines.append(f"- **série** : {s['name']} #{s['episode']} — « {s['continuityCTA']} »")
    lines += ["", "| # | rôle | gain | scène | narration |", "|---|------|------|-------|-----------|"]
    for i, (b, r) in enumerate(zip(data["blocks"], report["structure"]["sequence"])):
        lines.append(f"| {i + 1} | {r} | {b.get('informationGain', '-')} | {_scene(b)} | {b['text']} |")
    p = report["pacing"]
    lines += [
        "",
        f"Rythme ({p['durationSource']}) : {p['totalSec']} s au total (cible {p['targetDurationSec']} s), "
        f"hook {p['hookSec']} s, premier exemple chiffré à {p['secondsBeforeFirstConcreteExample']} s, "
        f"payoff à {p['secondsBeforePayoff']} s.",
        "",
        "Diagnostics : " + (
            "; ".join(f"`{i['code']}` ({i['severity']})" for i in report["issues"]) or "aucun problème détecté"
        ),
        "",
    ]
    return "\n".join(lines)


def _summary(path: Path) -> dict:
    data = load(path)
    report = retention.analyze(data)
    blocks = data["blocks"]
    p = report["pacing"]
    scenes = [_scene(b) for b in blocks]
    return {
        "title": data["title"],
        "hook": report["hook"]["text"],
        "hookWords": report["hook"]["wordCount"],
        "hookSec": p["hookSec"],
        "firstExample": p["secondsBeforeFirstConcreteExample"],
        "payoffSec": p["secondsBeforePayoff"],
        "total": p["totalSec"],
        "roles": report["structure"]["sequence"],
        "structureAvailable": report["structure"]["available"],
        "repeats": [i["code"] for i in report["repetition"]["issues"]],
        "payoff": (report["payoff"].get("text") or "—"),
        "payoffConcrete": report["payoff"]["concreteValue"],
        "payoffResolves": report["payoff"]["resolvesHook"],
        "cta": report["cta"]["text"],
        "ctaIntent": report["cta"]["declaredIntent"] or report["cta"]["detectedIntent"],
        "distinctScenes": len(set(scenes)),
        "scenes": scenes,
        "loops": len(report["openLoops"]),
        "issues": [f"{i['code']}" for i in report["issues"]],
    }


def comparison_section(name: str, before: Path, after: Path) -> str:
    b, a = _summary(before), _summary(after)
    rows = [
        ("Hook", f"« {b['hook']} » ({b['hookWords']} mots)", f"« {a['hook']} » ({a['hookWords']} mots)"),
        ("Durée du hook", f"{b['hookSec']} s", f"{a['hookSec']} s"),
        ("Premier élément chiffré", f"{b['firstExample']} s" if b["firstExample"] is not None else "aucun",
         f"{a['firstExample']} s" if a["firstExample"] is not None else "aucun"),
        ("Payoff à", f"{b['payoffSec']} s", f"{a['payoffSec']} s"),
        ("Durée totale (estimée)", f"{b['total']} s", f"{a['total']} s"),
        ("Progression narrative", " > ".join(b["roles"]) if b["structureAvailable"] else "non déclarée (aucun rôle de rétention)",
         " > ".join(a["roles"])),
        ("Boucles ouvertes déclarées", str(b["loops"]), str(a["loops"])),
        ("Informations répétées", ", ".join(b["repeats"]) or "aucune détectée", ", ".join(a["repeats"]) or "aucune détectée"),
        ("Payoff", f"« {b['payoff']} » — valeur concrète : {b['payoffConcrete']}",
         f"« {a['payoff']} » — valeur concrète : {a['payoffConcrete']}"),
        ("CTA", f"« {b['cta']} » ({b['ctaIntent']})", f"« {a['cta']} » ({a['ctaIntent']})"),
        ("Progression visuelle", f"{b['distinctScenes']} scène(s)/cadrage(s) distincts : {', '.join(b['scenes'])}",
         f"{a['distinctScenes']} scène(s)/cadrage(s) distincts : {', '.join(a['scenes'])}"),
        ("Problèmes détectés", ", ".join(b["issues"]) or "aucun", ", ".join(a["issues"]) or "aucun"),
    ]
    out = [f"### {name}", "", "| Critère | AVANT (script actuel) | APRÈS (Retention Engine, écrit à la main) |", "|---|---|---|"]
    out += [f"| {k} | {x} | {y} |" for k, x, y in rows]
    out.append("")
    return "\n".join(out)


def render_report() -> str:
    parts = [
        "# Retention Engine V1 — benchmark",
        "",
        "Généré par `scripts/retention_benchmark.py` : analyse **déterministe** (aucun appel IA, aucun rendu, "
        "aucune publication). Les chiffres de durée sont **estimés** depuis le nombre de mots (fr 213, en 172 mots/min) ; "
        "ils seront mesurés au rendu. Aucun score de viralité : seulement des caractéristiques structurelles.",
        "",
        "## 1. PocketLogic — 5 concepts",
        "",
    ]
    parts += [concept_section(p) for p in POCKETLOGIC]
    parts += [
        "## 2. Avant / après sur 3 scripts existants", "",
        "AVANT = scripts du benchmark Phase 2 tels qu'ils existent. APRÈS = réécriture manuelle selon "
        "l'architecture (pas une sortie du LLM : elle ne mesure pas le prompt, seulement ce que la structure change).", "",
    ]
    parts += [comparison_section(*row) for row in BEFORE_AFTER]
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    text = render_report()
    if args.print:
        sys.stdout.buffer.write(text.encode("utf-8"))
        return
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(f"écrit : {REPORT_PATH}")


if __name__ == "__main__":
    main()
