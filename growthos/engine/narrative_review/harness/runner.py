"""Harness comparatif A/B (P0-C) : SIMULATION HORS LIGNE uniquement. 20 cases = 5 sujets pilote x 2 strates x 2 conditions.

Garanties : un appel de rédaction par case et un appel de critique par script exploitable (40 appels logiques maximum), aucun retry,
budget réservé avant chaque tentative (tarif inconnu, prompt au-dessus du plafond de tokens ou plafond insuffisant = pas d'appel),
sortie jamais réparée, aucune fuite `evaluator_only`/holdout (vérifiée sur chaque payload), condition A/B jamais transmise au critique,
journal des tentatives ÉCRIT AU FIL DE L'EAU (une exception ne fait perdre aucune ligne), retry caché détecté = arrêt de la campagne.
Aucun fournisseur réel n'est fourni.
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
from ..providers import Budget, Prices, Provider, estimate_usd, max_call_usd, prompt_tokens_upper
from ..reviewer import MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS, TIMEOUT_S, Caller, review
from ..snapshot import FACTUALITY_TO_MODES, from_standard, from_story_visual
from . import policy
from .corpus import PILOT_IDS, assert_no_leak, generator_view

COLUMNS = ["campaign_id", "attempt_id", "task", "topic_id", "stratum", "condition", "repetition", "blind_script_id", "corpus_hash",
           "sources_hash", "policy_version", "prompt_version", "prompt_hash", "model", "model_config", "source_commit", "snapshot_id",
           "output_path", "execution_status", "error_code", "technical_valid", "editorial_decision", "logical_calls", "http_attempts",
           "input_tokens", "output_tokens", "usage_complete", "estimated_cost", "observed_cost", "cost_method", "currency", "latency_ms",
           "audio_mode", "measured_duration_s", "duration_estimator", "estimated_duration_s"]
HALTED = "HALTED_RETRY_DETECTED"


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
        if not isinstance(blocks, list) or not blocks or any(not isinstance(b, dict) for b in blocks):
            return False, ["blocks must be a non-empty list of objects"]
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


class _Journal:
    """Lignes en mémoire ET, si `out_dir`, ajoutées au CSV dès qu'elles existent : une exception ne perd aucune tentative payée."""

    def __init__(self, out_dir: Path | None):
        self.rows: list[dict] = []
        self.path = None
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            self.path = out_dir / "registre_executions.csv"
            self.path.write_text(registry_csv([]), encoding="utf-8")

    def add(self, row: dict) -> dict:
        self.rows.append(row)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8", newline="") as fh:
                csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n").writerow(row)
        return row


def run_campaign(corpus: dict, *, generator: Provider, critic: Provider, budget: Budget, gen_prices: Prices | None,
                 critic_prices: Prices | None, gen_model: str, critic_model: str, campaign_id: str, caller: Caller,
                 source_commit: str, out_dir: Path | None = None, allowed_splits=("pilot",), topic_ids=PILOT_IDS) -> dict:
    manifest = policy.load_manifest()
    cases = plan_cases(campaign_id, topic_ids)
    journal = _Journal(out_dir)
    pairs: dict[tuple, dict] = {}
    state = {"halted": False, "attempt_no": 0, "calls": {"generation": 0, "critique": 0}}
    for case in cases:
        view = generator_view(corpus, case["topic_id"], allowed_splits=allowed_splits)  # lève HoldoutAccessError hors campagne
        spec = policy.build_condition(case["stratum"], case["condition"], view, manifest)
        assert_no_leak(spec["system"] + "\n" + spec["user"], corpus, own_topic_id=case["topic_id"])
        state["attempt_no"] += 1
        base = {"campaign_id": campaign_id, "attempt_id": f"{campaign_id}-{state['attempt_no']:03d}", "topic_id": case["topic_id"],
                "stratum": case["stratum"], "condition": case["condition"], "repetition": 1, "blind_script_id": case["blind_script_id"],
                "corpus_hash": corpus["hashes"]["corpus_sha256"], "sources_hash": corpus["hashes"]["sources_sha256"],
                "policy_version": c.POLICY_VERSION, "prompt_version": spec["baseline_commit"], "prompt_hash": spec["prompt_sha256"],
                "model": gen_model, "model_config": f"max_in={MAX_INPUT_TOKENS};max_out={MAX_OUTPUT_TOKENS};timeout_s={TIMEOUT_S}",
                "source_commit": source_commit}
        pair = pairs.setdefault((case["topic_id"], case["stratum"]), {"topic_id": case["topic_id"], "stratum": case["stratum"]})
        entry = pair.setdefault(case["condition"], {"blind_script_id": case["blind_script_id"]})
        try:
            _one_case(case, spec, view, base, entry, journal, state, corpus, generator, critic, budget, gen_prices, critic_prices,
                      critic_model, caller, out_dir)
        except Exception as exc:  # noqa: BLE001 - un défaut du harness est journalisé ; la campagne continue, sans AUCUN retry
            journal.add(_row(base, task="harness", execution_status="harness_error", error_code=type(exc).__name__, logical_calls=0))
            entry.update(status="harness_error", error=type(exc).__name__)
    paired = [pairs[k] for k in sorted(pairs)]
    summary = _summary(journal.rows, paired, state["calls"], budget, campaign_id, manifest, corpus, source_commit, state["halted"])
    if out_dir is not None:
        (out_dir / "campaign_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"rows": journal.rows, "pairs": paired, "summary": summary}


def _one_case(case, spec, view, base, entry, journal, state, corpus, generator, critic, budget, gen_prices, critic_prices,
              critic_model, caller, out_dir) -> None:
    stratum, condition, topic_id = case["stratum"], case["condition"], case["topic_id"]
    if state["halted"]:
        journal.add(_row(base, task="generation", execution_status="not_run", error_code=HALTED, logical_calls=0, http_attempts=0))
        entry.update(status="not_run", error=HALTED)
        return
    if prompt_tokens_upper(spec["system"] + spec["user"]) > MAX_INPUT_TOKENS:
        journal.add(_row(base, task="generation", execution_status="not_run", error_code=c.INPUT_TOO_LARGE, logical_calls=0, http_attempts=0))
        entry.update(status="not_run", error=c.INPUT_TOO_LARGE)
        return
    try:
        budget.reserve(base["attempt_id"], max_call_usd(gen_prices, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS))
    except c.ReviewError as exc:
        journal.add(_row(base, task="generation", execution_status="not_run", error_code=exc.code, logical_calls=0, http_attempts=0))
        entry.update(status="not_run", error=exc.code)
        return
    state["calls"]["generation"] += 1
    started = time.monotonic()
    try:
        result = generator({"role": "generation", "system": spec["system"], "user": spec["user"],
                            "max_output_tokens": MAX_OUTPUT_TOKENS, "timeout_s": TIMEOUT_S})
    except Exception as exc:  # noqa: BLE001 - échec visible, coût inconnu, AUCUN retry
        budget.settle(base["attempt_id"], None)
        journal.add(_row(base, task="generation", execution_status="provider_error", error_code=type(exc).__name__, logical_calls=1,
                         cost_method="unknown", latency_ms=round((time.monotonic() - started) * 1000)))
        entry.update(status="provider_error", error=type(exc).__name__)
        return
    est = estimate_usd(result.usage, gen_prices)
    overrun = budget.settle(base["attempt_id"], est)
    if overrun or result.http_attempts is None or result.http_attempts > 1:
        state["halted"] = True  # retry interne, tentatives inconnues ou dépassement de réservation : la borne de coût n'est plus tenue
    usage = result.usage or {}
    usage_cols = dict(input_tokens=usage.get("input"), output_tokens=usage.get("output"), usage_complete=bool(result.usage),
                      estimated_cost=est, observed_cost=None, cost_method="tokens x configured prices" if est is not None else "unknown",
                      currency=gen_prices.currency if gen_prices else None,
                      latency_ms=None if result.latency_s is None else round(result.latency_s * 1000),
                      logical_calls=1, http_attempts=result.http_attempts)
    if overrun:
        usage_cols["cost_method"] = "tokens x configured prices (EXCEEDED reservation)"
    if result.text is None:
        journal.add(_row(base, task="generation", execution_status="no_output", error_code=result.error or "no_text", **usage_cols))
        entry.update(status="no_output", error=result.error)
        return
    output_path = None
    if out_dir is not None:
        output_path = out_dir / f"{case['blind_script_id']}.json"
        output_path.write_text(result.text, encoding="utf-8")  # sortie brute, jamais réparée
    valid, errors = technical_check(stratum, result.text)
    journal.add(_row(base, task="generation", execution_status="ok", technical_valid=valid, output_path=str(output_path or ""),
                     error_code="" if valid else "TECHNICAL_INVALID", **usage_cols))
    entry.update(status="ok", technical_valid=valid, technical_errors=errors, generation_cost=est)
    if not valid:
        entry["critique"] = "skipped_not_exploitable"
        return
    if state["halted"]:
        entry["critique"] = "skipped_" + HALTED
        return
    # Critique : un appel maximum, jamais l'étiquette de condition, jamais d'évaluateur.
    snapshot = _snapshot(stratum, result.text, view, caller)
    assert_no_leak(json.dumps(snapshot, ensure_ascii=False), corpus, own_topic_id=topic_id)
    if stratum == "story_visual":  # le mode du brief fait autorité ; un décalage avec la factualité du plan est signalé, pas masqué
        plan_modes = FACTUALITY_TO_MODES.get(json.loads(result.text).get("factuality"))
        entry["factuality_vs_brief_mismatch"] = plan_modes is None or plan_modes != (view["generator_input"]["truth_mode"],
                                                                                    view["generator_input"]["illustration_mode"])
    state["attempt_no"] += 1
    critic_id = f"{base['campaign_id']}-{state['attempt_no']:03d}"
    report = review(snapshot, critic, caller=caller, budget=budget, prices=critic_prices, model=critic_model)
    u = report["usage"]
    state["calls"]["critique"] += u["logical_calls"]   # un refus (budget, locataire, taille) vaut 0 appel, comme dans le journal
    answered_unverified = u["provider_attempts"] is None and report["error"] is None or "provider_attempts_unverified" in report["limits"]
    if u["logical_calls"] and ((u["provider_attempts"] or 0) > 1 or answered_unverified or "cost_exceeded_reservation" in report["limits"]):
        state["halted"] = True  # une exception ou un timeout isolé n'arrête pas la campagne (une case consommée, sans retry)
    journal.add(_row({**base, "attempt_id": critic_id, "model": critic_model, "prompt_version": c.PROMPT_VERSION, "prompt_hash": ""},
                     task="critique", snapshot_id=report["snapshot_id"], execution_status=report["analysis_status"],
                     error_code=(report["error"] or {}).get("code"), editorial_decision=report["decision"],
                     logical_calls=u["logical_calls"], http_attempts=u["provider_attempts"], input_tokens=u["input_tokens"],
                     output_tokens=u["output_tokens"], usage_complete=u["input_tokens"] is not None, estimated_cost=u["estimated_cost"],
                     observed_cost=u["observed_cost"], cost_method=u["cost_method"], currency=u["currency"],
                     latency_ms=None if u["latency_s"] is None else round(u["latency_s"] * 1000)))
    entry["critique"] = {"decision": report["decision"], "analysis_status": report["analysis_status"],
                         "error": (report["error"] or {}).get("code"), "estimated_cost": u["estimated_cost"],
                         "limits": report["limits"], "finding_codes": [f["code"] for f in (report["findings"] or [])]}


def _summary(rows, pairs, logical_calls, budget, campaign_id, manifest, corpus, source_commit, halted) -> dict:
    known = [r["estimated_cost"] for r in rows if r["estimated_cost"] not in ("", None)]
    return {"campaign_id": campaign_id, "mode": "offline_simulation", "source_commit": source_commit, "policy_version": c.POLICY_VERSION,
            "critic_version": c.CRITIC_VERSION, "halted_on_hidden_retry": halted,
            "baseline": {"standard_commit": manifest["standard"]["source_commit"],
                         "story_visual_commit": manifest["story_visual"]["source_commit"]},
            "corpus_sha256": corpus["hashes"]["corpus_sha256"], "sources_sha256": corpus["hashes"]["sources_sha256"],
            "logical_calls": logical_calls, "logical_calls_total": sum(logical_calls.values()), "attempts_logged": len(rows),
            "errors": [{"attempt_id": r["attempt_id"], "task": r["task"], "status": r["execution_status"], "code": r["error_code"]}
                       for r in rows if r["error_code"] not in ("", None) or r["execution_status"] not in ("ok", "complete")],
            "costs": {"estimated_known_usd": sum(known) if known else None, "attempts_with_unknown_cost": sum(1 for r in rows if r["estimated_cost"] in ("", None) and r["logical_calls"] != 0),
                      "observed_usd": None, "budget_ceiling_usd": budget.ceiling_usd, "budget_committed_usd": budget.committed(),
                      "reservation_overruns": budget.overruns},
            "pairs": pairs}
