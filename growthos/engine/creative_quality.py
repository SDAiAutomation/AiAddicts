"""Read-only creative quality report composed from existing Faceloop diagnostics.

No LLM calls, mutations, scoring changes or publication side effects.
"""
from __future__ import annotations

from . import editorial_quality, retention

SCHEMA_VERSION = "creative_quality:v1"

_ACTIONS = {
    "arithmetic_inconsistency": "Vérifier et corriger uniquement le calcul signalé.",
    "projection_assumption_missing": "Préciser les hypothèses de la projection.",
    "guaranteed_language": "Remplacer la garantie par une formulation prudente et vérifiable.",
    "role_label_leak": "Retirer l'étiquette interne du texte destiné au spectateur.",
    "viewer_placeholder": "Remplacer le texte de remplissage par une valeur vérifiée.",
    "unsupported_cta_promise": "Supprimer la promesse non tenue ou fournir réellement la ressource.",
    "hook_too_long": "Raccourcir le hook en conservant sa promesse.",
    "cta_too_long": "Raccourcir le CTA sans changer son intention.",
}

# Pure length limits of editorial_quality (title, CTA) are informational: blind test of 30 real
# rewrites (2026-10-11) preferred the original title 7 times out of 8, and no performance data
# supports the 60-character cap. shortcut: matches the French messages of editorial_quality by
# prefix; test_length_messages_still_match_editorial_quality fails if they drift.
_LENGTH_ONLY_PREFIXES = ("Titre de ", "CTA trop long")


def _issue(item: dict, blocks: list[dict]) -> dict:
    code = str(item.get("code") or "unknown")
    indices = item.get("blocks") or []
    # Existing retention reports use 0-based block indices.
    index = indices[0] if isinstance(indices, list) and indices and type(indices[0]) is int else None
    if index is not None and not (0 <= index < len(blocks)):
        index = None
    evidence = ""
    if index is not None and 0 <= index < len(blocks):
        evidence = str(blocks[index].get("text") or "")[:180]
    blocking = code in retention.BLOCKING_CODES
    return {
        "code": code,
        "severity": "blocking" if blocking else "warning" if item.get("severity") == "high" else "info",
        "source": "retention",
        "block_index": index,
        "evidence": evidence,
        "reason": str(item.get("message") or ""),
        "suggested_action": _ACTIONS.get(code, "Examiner le passage signalé avant toute correction."),
        "confidence": "deterministic" if blocking else "heuristic",
    }


def analyze(script: dict, *, retention_report: dict | None = None,
            editorial_report: dict | None = None) -> dict:
    """Build a shadow-only report; a 'block' decision is informational here."""
    blocks = [b for b in (script.get("blocks") or []) if isinstance(b, dict)]
    retained = retention_report if retention_report is not None else retention.analyze(script)
    editorial = editorial_report if editorial_report is not None else editorial_quality.analyze_script(script)
    issues = [_issue(i, blocks) for i in retained.get("issues", []) if isinstance(i, dict)]
    for reason in editorial.get("issues", []):
        reason = str(reason)
        length_only = reason.startswith(_LENGTH_ONLY_PREFIXES)
        issues.append({
            "code": "editorial_length" if length_only else "editorial_heuristic",
            "severity": "info" if length_only else "warning",
            "source": "editorial",
            "block_index": None,
            "evidence": "",
            "reason": reason,
            "suggested_action": "Optionnel : à raccourcir seulement si le texte y gagne."
            if length_only else "Vérifier le diagnostic éditorial et modifier uniquement si pertinent.",
            "confidence": "heuristic",
        })
    decision = "block" if any(i["severity"] == "blocking" for i in issues) else (
        "review" if any(i["severity"] == "warning" for i in issues) else "pass"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "script",
        "decision": decision,
        "issues": issues,
        "automatic_edits_applied": False,
        "enforcement_enabled": False,
        "editorial_score_existing": editorial.get("score"),
        "retention_engine_version": retained.get("version"),
    }


def combine(script_report: dict, render_report: dict | None = None) -> dict:
    """Aggregate independent stage decisions without changing enforcement."""
    reports = [script_report] + ([render_report] if render_report is not None else [])
    if any(r.get("decision") == "block" for r in reports):
        decision = "block"
    elif any(r.get("decision") == "review" for r in reports):
        decision = "review"
    else:
        decision = "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "combined",
        "decision": decision,
        "issues": [issue for report in reports for issue in report.get("issues", [])],
        "automatic_edits_applied": False,
        "enforcement_enabled": False,
        "stages_checked": [report.get("stage") for report in reports],
    }
