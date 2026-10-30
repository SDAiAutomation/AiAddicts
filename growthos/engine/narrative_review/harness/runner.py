"""Harness comparatif A/B (P0-C) : SIMULATION HORS LIGNE uniquement. 20 cases = 5 sujets pilote x 2 strates x 2 conditions.

Garanties : un appel de rédaction par case et un appel de critique par script exploitable (40 appels logiques maximum), aucun retry,
budget réservé avant chaque tentative (tarif inconnu ou plafond insuffisant = pas d'appel), sortie jamais réparée, aucune fuite
`evaluator_only`/holdout (vérifiée sur chaque payload), condition A/B jamais transmise au critique, journal complet des
tentatives (erreurs, versions, tokens, coûts estimés/observés séparés, inconnus = vide). Aucun fournisseur réel n'est fourni.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import time
from pathlib import Path

from .. import contract as c
from ..providers import Budget, Prices, Provider, estimate_usd, max_call_usd
from ..reviewer import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS, TIMEOUT_S, Caller, review
from ..snapshot import from_standard, from_story_visual
from . import policy
from .corpus import PILOT_IDS, assert_no_leak, generator_view, sha256_text

COLUMNS = ["campaign_id", "attempt_id", "task", "topic_id", "stratum", "condition", "repetition", "blind_script_id", "corpus_hash",
           "sources_hash", "policy_version", "prompt_version", "prompt_hash", "model", "model_config", "source_commit", "snapshot_id",
           "output_path", "execution_status", "error_code", "technical_valid", "editorial_decision", "logical_calls", "http_attempts",
           "input_tokens", "output_tokens", "usage_complete", "estimated_cost", "observed_cost", "cost_method", "currency", "latency_ms",
           "audio_mode", "measured_duration_s", "duration_estimator", "estimated_duration_s"]


def plan_cases(campaign_id: str, topic_ids=PILOT_IDS) -> list[dict]:
    """Ordre déterministe + identifiants aveugles dérivés d'une permutation seedée par la campagne (pas de fuite d'ordre A/B)."""
    cases = [{"topic_id": t, "stratum": s, "condition": cond} for t in sorted(topic_ids) for s in policy.STRATA for cond in policy.CONDITIONS]
    ranked = sorted(cases, key=lambda k: hashlib.sha256(f"{campaign_id}|{k['topic_id']}|{k['stratum']}|{k['condition']}".encode()).hexdigest())
    blind = {(k["topic_id"], k["stratum"], k["condition"]): f"B{i + 1:02d}" for i, k in enumerate(ranked)}
    return [{**k, "blind_script_id": blind[(k["topic_id"], k["stratum"], k["condition"])]} for k in cases]


# --- Validité technique (lecture seule : la sortie n'est JAMAIS modifiée) ---------------------------------------------------

def _words(text: str) -> int:
    return len(text.split())


def technical_check(stratum: str, text: str) -> tuple[bool, list[str]]:
    """Validité du FORMAT, notée séparément du jugement narratif. Un JSON invalide reste un échec compté, jamais réparé."""
    try:
        data = json.loads(text)
    except ValueError:
        return False, ["output is not valid JSON"]
    if not isinstance(data, dict):
        return False, ["output is not a JSON object"]
    errors: list[str] = []
    if stratum == "standard":
        blocks = data.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            return False, ["blocks missing"]
        try:  # validateur de production en lecture, sur une COPIE complétée des champs que la production ajoute elle-même
            from ... import script as script_module
            probe = copy.deepcopy(data)
            probe.setdefault("niche", "benchmark")
            probe.setdefault("account", "benchmark")
            script_module.validate_script(script_module.normalize_script(probe))
        except ValueError as exc:
            errors.append(f"validate_script: {exc}")
        except Exception as exc:  # noqa: BLE001 - dépendance de normalisation indisponible : on le dit, on ne l'ignore pas
            errors.append(f"validate_script unavailable: {type(exc).__name__}")
        if blocks[0].get("role") != "hook" or _words(str(blocks[0].get("text", ""))) > 10:
            errors.append("first block must be a hook of at most 10 words")
    else:
        scenes = data.get("scenes")
        # shortcut: contrôle STRUCTUREL seulement ; le validateur Story Visual v1 vit dans la PR #103, absent de cette base. À remplacer
        # par `story_visual.schema.validate_story_plan` quand #103 est fusionnée, sinon la conformité de format n'est pas mesurée.
        if not isinstance(scenes, list) or not 6 <= len(scenes) <= 14:
            errors.append("scenes must hold 6..14 items (structural check only, not the v1 validator)")
        elif any(not isinstance(s, dict) or not isinstance(s.get("narration"), str) for s in scenes):
            errors.append("each scene needs a narration")
        if data.get("factuality") not in ("verified", "inspired", "fiction", "metaphor"):
            errors.append("factuality must be verified, inspired, fiction or metaphor")
    return not errors, errors


def _snapshot(stratum: str, text: str, view: dict, caller: Caller) -> dict:
    gi = view["generator_input"]
    data = json.loads(text)
    ctx = dict(organization_id=caller.organization_id, account_id=caller.account_id, language=view["defaults"]["language"],
               truth_mode=gi["truth_mode"], illustration_mode=gi["illustration_mode"], sources=view["sources"],
               intent={k: gi[k] for k in ("central_question", "learning_intention", "constraints", "prohibited_claims")} | {"audience": view["defaults"]["audience"]})
    return from_standard(data, **ctx) if stratum == "standard" else from_story_visual(data, **ctx)


# --- Journal ---------------------------------------------------------------------------------------------------------------

def _row(base: dict, **kw) -> dict:
    row = {k: "" for k in COLUMNS}
    row.update(base)
    for k, v in kw.items():
        row[k] = "" if v is None else v
    return row


def registry_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def run_campaign(corpus: dict, *, generator: Provider, critic: Provider, budget: Budget, gen_prices: Prices | None,
                 critic_prices: Prices | None, gen_model: str, critic_model: str, campaign_id: str, caller: Caller,
                 source_commit: str, out_dir: Path | None = None, allowed_splits=("pilot",), topic_ids=PILOT_IDS) -> dict:
    manifest = policy.load_manifest()
    cases = plan_cases(campaign_id, topic_ids)
    rows: list[dict] = []
    pairs: dict[tuple, dict] = {}
    logical_calls = {"generation": 0, "critique": 0}
    attempt_no = 0
    for case in cases:
        topic_id, stratum, condition = case["topic_id"], case["stratum"], case["condition"]
        view = generator_view(corpus, topic_id, allowed_splits=allowed_splits)  # lève HoldoutAccessError hors campagne
        spec = policy.build_condition(stratum, condition, view, manifest)
        payload = spec["system"] + "\n" + spec["user"]
        assert_no_leak(payload, corpus, own_topic_id=topic_id)
        attempt_no += 1
        base = {"campaign_id": campaign_id, "attempt_id": f"{campaign_id}-{attempt_no:03d}", "topic_id": topic_id, "stratum": stratum,
                "condition": condition, "repetition": 1, "blind_script_id": case["blind_script_id"],
                "corpus_hash": corpus["hashes"]["corpus_sha256"], "sources_hash": corpus["hashes"]["sources_sha256"],
                "policy_version": c.POLICY_VERSION, "prompt_version": spec["baseline_commit"], "prompt_hash": spec["prompt_sha256"],
                "model": gen_model, "model_config": f"max_in={MAX_INPUT_TOKENS};max_out={MAX_OUTPUT_TOKENS};timeout_s={TIMEOUT_S}",
                "source_commit": source_commit}
        pair = pairs.setdefault((topic_id, stratum), {"topic_id": topic_id, "stratum": stratum})
        entry = pair.setdefault(condition, {"blind_script_id": case["blind_script_id"]})
        try:
            budget.reserve(base["attempt_id"], max_call_usd(gen_prices, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS))
        except c.ReviewError as exc:
            rows.append(_row(base, task="generation", execution_status="not_run", error_code=exc.code, logical_calls=0, http_attempts=0))
            entry.update(status="not_run", error=exc.code)
            continue
        logical_calls["generation"] += 1
        started = time.monotonic()
        try:
            result = generator({"role": "generation", "system": spec["system"], "user": spec["user"],
                                "max_output_tokens": MAX_OUTPUT_TOKENS, "timeout_s": TIMEOUT_S})
        except Exception as exc:  # noqa: BLE001 - échec visible, coût inconnu, AUCUN retry
            budget.settle(base["attempt_id"], None)
            rows.append(_row(base, task="generation", execution_status="provider_error", error_code=type(exc).__name__, logical_calls=1,
                             cost_method="unknown", latency_ms=round((time.monotonic() - started) * 1000)))
            entry.update(status="provider_error", error=type(exc).__name__)
            continue
        est = estimate_usd(result.usage, gen_prices)
        budget.settle(base["attempt_id"], est)
        usage = result.usage or {}
        usage_cols = dict(input_tokens=usage.get("input"), output_tokens=usage.get("output"), usage_complete=bool(result.usage),
                          estimated_cost=est, observed_cost=None, cost_method="tokens x configured prices" if est is not None else "unknown",
                          currency=gen_prices.currency if gen_prices else None,
                          latency_ms=None if result.latency_s is None else round(result.latency_s * 1000),
                          logical_calls=1, http_attempts=result.http_attempts)
        if result.text is None:
            rows.append(_row(base, task="generation", execution_status="no_output", error_code=result.error or "no_text", **usage_cols))
            entry.update(status="no_output", error=result.error)
            continue
        output_path = None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{case['blind_script_id']}.json"
            output_path.write_text(result.text, encoding="utf-8")  # sortie brute, jamais réparée
        valid, errors = technical_check(stratum, result.text)
        rows.append(_row(base, task="generation", execution_status="ok", technical_valid=valid, output_path=str(output_path or ""),
                         error_code="" if valid else "TECHNICAL_INVALID", **usage_cols))
        entry.update(status="ok", technical_valid=valid, technical_errors=errors, generation_cost=est)
        if not valid:
            entry["critique"] = "skipped_not_exploitable"
            continue
        # Critique : un appel maximum, jamais l'étiquette de condition, jamais d'évaluateur.
        snapshot = _snapshot(stratum, result.text, view, caller)
        assert_no_leak(json.dumps(snapshot, ensure_ascii=False), corpus, own_topic_id=topic_id)
        attempt_no += 1
        critic_id = f"{campaign_id}-{attempt_no:03d}"
        logical_calls["critique"] += 1
        report = review(snapshot, critic, caller=caller, budget=budget, prices=critic_prices, model=critic_model)
        u = report["usage"]
        rows.append(_row({**base, "attempt_id": critic_id, "model": critic_model, "prompt_version": c.PROMPT_VERSION, "prompt_hash": ""},
                         task="critique", snapshot_id=report["snapshot_id"], execution_status=report["analysis_status"],
                         error_code=(report["error"] or {}).get("code"), editorial_decision=report["decision"],
                         logical_calls=u["logical_calls"], http_attempts=u["provider_attempts"], input_tokens=u["input_tokens"],
                         output_tokens=u["output_tokens"], usage_complete=u["input_tokens"] is not None, estimated_cost=u["estimated_cost"],
                         observed_cost=u["observed_cost"], cost_method=u["cost_method"], currency=u["currency"],
                         latency_ms=None if u["latency_s"] is None else round(u["latency_s"] * 1000)))
        entry["critique"] = {"decision": report["decision"], "analysis_status": report["analysis_status"],
                             "error": (report["error"] or {}).get("code"), "estimated_cost": u["estimated_cost"],
                             "finding_codes": [f["code"] for f in (report["findings"] or [])]}
    paired = [pairs[k] for k in sorted(pairs)]
    summary = _summary(rows, paired, logical_calls, budget, campaign_id, manifest, corpus, source_commit)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "registre_executions.csv").write_text(registry_csv(rows), encoding="utf-8")
        (out_dir / "campaign_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"rows": rows, "pairs": paired, "summary": summary}


def _summary(rows, pairs, logical_calls, budget, campaign_id, manifest, corpus, source_commit) -> dict:
    known = [r["estimated_cost"] for r in rows if r["estimated_cost"] not in ("", None)]
    return {"campaign_id": campaign_id, "mode": "offline_simulation", "source_commit": source_commit, "policy_version": c.POLICY_VERSION,
            "critic_version": c.CRITIC_VERSION, "baseline": {"standard_commit": manifest["standard"]["source_commit"],
                                                            "story_visual_commit": manifest["story_visual"]["source_commit"]},
            "corpus_sha256": corpus["hashes"]["corpus_sha256"], "sources_sha256": corpus["hashes"]["sources_sha256"],
            "logical_calls": logical_calls, "logical_calls_total": sum(logical_calls.values()), "attempts_logged": len(rows),
            "errors": [{"attempt_id": r["attempt_id"], "task": r["task"], "status": r["execution_status"], "code": r["error_code"]}
                       for r in rows if r["error_code"] not in ("", None) or r["execution_status"] not in ("ok", "complete")],
            "costs": {"estimated_known_usd": sum(known) if known else None, "attempts_with_unknown_cost": sum(1 for r in rows if r["estimated_cost"] in ("", None)),
                      "observed_usd": None, "budget_ceiling_usd": budget.ceiling_usd, "budget_committed_usd": budget.committed()},
            "pairs": pairs}
