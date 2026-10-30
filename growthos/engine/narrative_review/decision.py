"""Décision SERVEUR, déterministe. Le modèle ne choisit ni `can_auto_accept`, ni la décision, ni un prix (clés rejetées).

Ordre des règles = tableau de 03_CONTRAT_CRITIQUE.md §6. Les avertissements ne se compensent pas et n'annulent aucun blocker.
`can_auto_accept` n'a de sens que dans le harness : même `accept` ne déclenche ni média, ni publication, ni changement de statut.
"""
from __future__ import annotations


def _judgement(snapshot: dict, response: dict | None, analysis_status: str) -> tuple[str, list[str]]:
    """Décision sur la seule qualité du jugement, avant le verrou de provenance des sources."""
    if analysis_status != "complete" or response is None:
        return "review", [f"analysis_{analysis_status}"]
    reasons: list[str] = []
    if snapshot["truth_mode"] == "unknown":
        reasons.append("truth_mode_unknown")
    reasons += [f"coverage_{c['dimension']}_{c['status']}" for c in response["coverage"] if c["status"] in ("partial", "unavailable")]
    reasons += [f"unverified_claim_{c['claim_id']}" for c in response["claims"] if c["assessment"] == "unverified"]
    blockers = [f for f in response["findings"] if f["severity"] == "blocker"]
    reasons += [f"uncertain_blocker_{f['finding_id']}" for f in blockers if f["assessment"] == "uncertain"]
    reasons += [f"needs_{f['repair_scope'][6:]}_{f['finding_id']}" for f in blockers
                if f["repair_scope"] in ("needs_sources", "needs_author")]
    if reasons:
        return "review", reasons
    if blockers:
        return "revise", [f"established_blocker_{f['finding_id']}" for f in blockers]
    if any(f["severity"] == "warning" for f in response["findings"]):
        return "accept_with_notes", []
    return "accept", []


def decide(snapshot: dict, response: dict | None, analysis_status: str = "complete") -> dict:
    judged, reasons = _judgement(snapshot, response, analysis_status)
    sources = snapshot["sources"]
    # Verrou de provenance : un dossier `prepared_for_benchmark` permet de COMPARER, pas de valider un document.
    evidence_human_verified = bool(sources) and all(s["verification"] == "human_verified" for s in sources)
    locked = bool(sources) and not evidence_human_verified
    decision = "review" if locked and judged in ("accept", "accept_with_notes") else judged
    if locked and judged != decision:
        reasons = reasons + ["evidence_not_human_verified"]
    return {"decision": decision, "judgement_decision": judged, "reasons": reasons,
            "can_auto_accept": decision in ("accept", "accept_with_notes"),
            "evidence_human_verified": evidence_human_verified}
