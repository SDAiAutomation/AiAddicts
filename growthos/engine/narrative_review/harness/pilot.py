"""Préparation HORS LIGNE du pilote P0-D Standard (5 sujets x A/B = 10 scripts). Ne lance AUCUN pilote : répétition à blanc avec fournisseurs factices.

    python -m growthos.engine.narrative_review.harness.pilot --out <dossier>

Périmètre fixé par le protocole : sujets N01, N04, N05, N13, N18 (split `pilot`), strate `standard` uniquement (Story Visual est exclu de ce
lot : son validateur v1 vit dans la PR #103), deux conditions A/B, un appel de rédaction par case et au plus un appel de critique par script
exploitable, soit 20 appels logiques au maximum. Aucun sujet de développement ou de réserve, aucune donnée `evaluator_only`, aucun retry.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import contract as c
from ..providers import Budget, Prices
from ..reviewer import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS, Caller
from . import policy
from .corpus import PILOT_IDS, assert_no_leak, generator_view, load_corpus
from .runner import run_campaign
from .simulation import simulated_critic, simulated_generator

PILOT_STRATA = ("standard",)
# Tarifs FICTIFS pour la répétition à blanc : ils rendent la réservation et le journal observables, ils ne sont pas un tarif réel.
ILLUSTRATIVE_PRICES = Prices(input_per_m=1.0, output_per_m=4.0, currency="USD", as_of="n/a", source="ILLUSTRATIVE PLACEHOLDER, not a real tariff")
# Hypothèses de taille (à remplacer par des mesures au premier essai réel) : sortie d'un script Standard et d'une critique, en jetons.
ASSUMED_OUTPUT_TOKENS = {"generation": (1500, 3000), "critique": (1000, 2500)}
ASSUMED_CRITIC_TEXT_CHARS = (3000, 6000)   # script (titre + blocs) + dossiers sources + intention, hors gabarit du critique


def conditions_report(corpus: dict, manifest: dict | None = None) -> list[dict]:
    """Pour chaque sujet pilote : A et B ne diffèrent QUE par la politique. Lève si ce n'est pas vrai."""
    manifest = manifest or policy.load_manifest()
    rows = []
    for tid in sorted(PILOT_IDS):
        view = generator_view(corpus, tid, allowed_splits=("pilot",))
        a = policy.build_condition("standard", "A", view, manifest)
        b = policy.build_condition("standard", "B", view, manifest)
        rebuilt_b, diff = policy.standard_B(a["system"])
        problems = []
        if a["user"] != b["user"]:
            problems.append("user message differs between A and B")
        if rebuilt_b != b["system"] or b["policy_diff"] != diff:
            problems.append("B is not exactly A plus the declared policy edits")
        if a["policy_diff"] != [] or a["baseline_commit"] != b["baseline_commit"] or a["policy_version"] != b["policy_version"]:
            problems.append("baseline commit or policy version differs")
        for spec in (a, b):
            assert_no_leak(spec["system"] + "\n" + spec["user"], corpus, own_topic_id=tid)
        if problems:
            raise AssertionError(f"{tid}: " + "; ".join(problems))
        rows.append({"topic_id": tid, "split": corpus["topics"][tid]["split"], "A_prompt_sha256": a["prompt_sha256"],
                     "B_prompt_sha256": b["prompt_sha256"], "user_sha256": policy.sha256_text(a["user"]),
                     "A_chars": len(a["system"]) + len(a["user"]), "B_chars": len(b["system"]) + len(b["user"]),
                     "policy_diff": [d["id"] for d in diff], "sources": corpus["topics"][tid]["generator_input"]["source_ids"]})
    return rows


def projected_usage(rows: list[dict], prices: Prices | None = None) -> dict:
    """Estimation du pilote (PAS une mesure). Entrée : taille réelle des prompts figés, 2 à 4 caractères par jeton ; sorties : hypothèses."""
    gen_chars = sum(r["A_chars"] + r["B_chars"] for r in rows)
    cases = 2 * len(rows)
    gen_in = (gen_chars // 4, gen_chars // 2)
    crit_template = 2300
    crit_in = tuple(cases * (crit_template + t) // d for t, d in zip(ASSUMED_CRITIC_TEXT_CHARS, (4, 2)))
    gen_out = tuple(cases * t for t in ASSUMED_OUTPUT_TOKENS["generation"])
    crit_out = tuple(cases * t for t in ASSUMED_OUTPUT_TOKENS["critique"])
    ceiling = {"input": 2 * cases * MAX_INPUT_TOKENS, "output": 2 * cases * MAX_OUTPUT_TOKENS, "logical_calls": 2 * cases}
    total_in, total_out = (gen_in[0] + crit_in[0], gen_in[1] + crit_in[1]), (gen_out[0] + crit_out[0], gen_out[1] + crit_out[1])
    usd = None
    if prices is not None:
        usd = {"expected_low": (total_in[0] * prices.input_per_m + total_out[0] * prices.output_per_m) / 1e6,
               "expected_high": (total_in[1] * prices.input_per_m + total_out[1] * prices.output_per_m) / 1e6,
               "ceiling": (ceiling["input"] * prices.input_per_m + ceiling["output"] * prices.output_per_m) / 1e6,
               "basis": prices.source or "configured prices"}
    return {"kind": "ESTIMATE_NOT_MEASUREMENT", "cases": cases, "tokens_expected": {"input": total_in, "output": total_out},
            "tokens_ceiling": ceiling, "usd": usd, "excludes": "billed reasoning tokens, provider-side overhead, retries (none allowed)",
            "assumptions": {"chars_per_token": "2 (upper) to 4 (lower)", "output_tokens": ASSUMED_OUTPUT_TOKENS,
                            "critic_text_chars": ASSUMED_CRITIC_TEXT_CHARS, "critic_template_chars": crit_template}}


def rehearse(out_dir: Path, *, campaign_id: str = "P0D-STANDARD-REHEARSAL") -> dict:
    """Répétition à blanc complète (10 cases) avec des fournisseurs FACTICES, sous la garde hors ligne du runner. Écrit le dossier d'audit."""
    corpus = load_corpus()
    rows = conditions_report(corpus)
    generator, critic = simulated_generator(), simulated_critic()
    result = run_campaign(corpus, generator=generator, critic=critic, budget=Budget(5.0), gen_prices=ILLUSTRATIVE_PRICES,
                          critic_prices=ILLUSTRATIVE_PRICES, gen_model="simulated-generator", critic_model="simulated-critic",
                          campaign_id=campaign_id, caller=Caller("rehearsal-org", "rehearsal-account"), source_commit="rehearsal",
                          out_dir=out_dir, allowed_splits=("pilot",), topic_ids=PILOT_IDS, strata=PILOT_STRATA)
    projection = projected_usage(rows)
    dossier = {"conditions": rows, "projection": projection, "summary": result["summary"]}
    (out_dir / "pilot_preparation.json").write_text(json.dumps(dossier, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"rows": result["rows"], "summary": result["summary"], "conditions": rows, "projection": projection,
            "generator_requests": generator.requests, "critic_requests": critic.requests}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="dossier d'audit de la répétition à blanc (créé)")
    args = parser.parse_args(argv)
    out = rehearse(args.out)
    s = out["summary"]
    print(json.dumps({"mode": s["mode"], "strata": s["strata"], "cases": len(out["conditions"]) * 2, "logical_calls": s["logical_calls_total"],
                      "network_attempts_blocked": s["network"]["attempts_blocked"], "halted": s["halted_on_hidden_retry"],
                      "projection": out["projection"]["tokens_expected"], "kind": out["projection"]["kind"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
