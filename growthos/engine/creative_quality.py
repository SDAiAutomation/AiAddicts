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


def _issue(item: dict, blocks: list[dict]) -> dict:
    code = str(item.get("code") or "unknown")
    indices = item.get("blocks") or []
    # Existing retention reports use 0-based block indices.
    index = indices[0] if isinstance(indices, list) and indices and isinstance(indices[0], int) else None
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
    blocks = script.get("blocks") if isinstance(script.get("blocks"), list) else []
    retained = retention_report if retention_report is not None else retention.analyze(script)
    editorial = editorial_report if editorial_report is not None else editorial_quality.analyze_script(script)
    issues = [_issue(i, blocks) for i in retained.get("issues", [])]
    for reason in editorial.get("issues", []):
        issues.append({
            "code": "editorial_heuristic",
            "severity": "warning",
            "source": "editorial",
            "block_index": None,
            "evidence": "",
            "reason": str(reason),
            "suggested_action": "Vérifier le diagnostic éditorial et modifier uniquement si pertinent.",
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
    }
