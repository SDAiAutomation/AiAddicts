"""Checklist de validation HUMAINE des sources du pilote (S01, S02 pour N05). Ce module ne déclare JAMAIS une source vérifiée.

- `build_checklist` produit un gabarit : une ligne par phrase du dossier à vérifier, tous les états à `unverified`, identité et dates à `null`.
- `validate_record` contrôle qu'un enregistrement REMPLI par un humain est complet et cohérent. Même complet, il ne modifie aucun fichier : c'est au propriétaire de reporter
  `human_verified_by` / `human_verified_at` dans `sources_bornees.json` (nouvelle version du corpus => nouvelle empreinte => nouvelle autorisation).
- Tant que le dossier est `prepared_for_benchmark`, la décision du critique reste `review` (verrou de provenance de `decision.py`).
"""
from __future__ import annotations

import re
from datetime import date

CLAIM_STATES = ("unverified", "verified", "partially_supported", "not_supported", "source_unavailable")
DECISIONS = ("human_verified", "needs_fix", "rejected")
CHECKS = ("page_reachable_at_accessed_url", "summary_is_original_not_a_copy", "locator_points_to_the_right_passage", "allowed_claims_within_what_the_page_says",
          "limitations_are_accurate")
MAX_QUOTE = 300


def required_source_ids(corpus: dict) -> list[str]:
    """Sources des sujets pilote en mode `fact` : celles dont la validation humaine conditionne une décision documentaire."""
    ids: set[str] = set()
    for topic in corpus["topics"].values():
        gi = topic["generator_input"]
        if topic["split"] == "pilot" and gi["truth_mode"] == "fact":
            ids.update(gi["source_ids"])
    return sorted(ids)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def build_checklist(corpus: dict) -> dict:
    sources = []
    for sid in required_source_ids(corpus):
        src = corpus["sources"][sid]
        sources.append({
            "source_id": sid, "title": src["title"], "url": src["url"], "accessed_at": src["accessed_at"], "locator": src["locator"],
            "allowed_claims": src["allowed_claims"], "limitations": src["limitations"],
            "checks": {name: {"state": "unverified", "note": None} for name in CHECKS},
            "claims": [{"claim_id": f"{sid}-C{i:02d}", "summary_sentence": sentence, "state": "unverified", "page_quote": None, "checked_on": None, "note": None}
                       for i, sentence in enumerate(_sentences(src["content"]), 1)],
            "decision": None})
    return {"version": "narrative-source-validation:0.1", "sources_sha256": corpus["hashes"]["sources_sha256"], "status": "TEMPLATE_NOT_VERIFIED",
            "verifier": {"name": None, "role": None, "independent_of_authors": None, "signed_on": None}, "sources": sources,
            "instructions": ("Open each URL yourself. For every summary sentence, copy a SHORT verbatim quote from the page (<= 300 characters) that supports it, or set the state to "
                             "partially_supported / not_supported / source_unavailable. Do not rely on the summary. A source is human_verified only if every claim is verified and every check is "
                             "verified. Nothing here changes the corpus: the owner reports the result in sources_bornees.json.")}


def validate_record(record: dict, corpus: dict) -> list[str]:
    """Problèmes d'un enregistrement rempli (vide = structurellement complet). Ne prouve PAS que la vérification a été bien faite : seule la relecture du propriétaire le fait."""
    problems: list[str] = []
    template = build_checklist(corpus)
    if record.get("sources_sha256") != template["sources_sha256"]:
        problems.append("sources_sha256 does not match the current corpus sources (the record is for another version)")
    v = record.get("verifier") or {}
    for key in ("name", "role", "signed_on"):
        if not isinstance(v.get(key), str) or not v[key].strip():
            problems.append(f"verifier.{key} is required")
    if v.get("independent_of_authors") is not True:
        problems.append("the verifier must be independent of the authors of the sources and scripts (independent_of_authors: true)")
    try:
        date.fromisoformat(str(v.get("signed_on")))
    except ValueError:
        problems.append("verifier.signed_on must be an ISO date")
    by_id = {s.get("source_id"): s for s in record.get("sources", [])}
    if set(by_id) != {s["source_id"] for s in template["sources"]}:
        problems.append("the record must cover exactly the required sources")
    for tpl in template["sources"]:
        src = by_id.get(tpl["source_id"])
        if not src:
            continue
        sid = tpl["source_id"]
        if [c.get("claim_id") for c in src.get("claims", [])] != [c["claim_id"] for c in tpl["claims"]] or \
           [c.get("summary_sentence") for c in src.get("claims", [])] != [c["summary_sentence"] for c in tpl["claims"]]:
            problems.append(f"{sid}: claims differ from the checklist (do not edit the summary sentences: report a needed fix in `note`)")
            continue
        for name in CHECKS:
            check = (src.get("checks") or {}).get(name) or {}
            if check.get("state") not in CLAIM_STATES or check["state"] == "unverified":
                problems.append(f"{sid}: check {name} has no decision")
        for claim in src["claims"]:
            if claim.get("state") not in CLAIM_STATES or claim["state"] == "unverified":
                problems.append(f"{claim.get('claim_id')}: no decision")
            elif claim["state"] == "verified":
                quote = claim.get("page_quote")
                if not isinstance(quote, str) or not 10 <= len(quote) <= MAX_QUOTE:
                    problems.append(f"{claim['claim_id']}: a verified claim needs a verbatim page quote of 10..{MAX_QUOTE} characters")
                if not claim.get("checked_on"):
                    problems.append(f"{claim['claim_id']}: checked_on is required")
        everything_verified = all(c.get("state") == "verified" for c in src["claims"]) and all(
            (src.get("checks") or {}).get(n, {}).get("state") == "verified" for n in CHECKS)
        if src.get("decision") not in DECISIONS:
            problems.append(f"{sid}: decision must be one of {DECISIONS}")
        elif src["decision"] == "human_verified" and not everything_verified:
            problems.append(f"{sid}: human_verified is impossible while a claim or a check is not verified")
    return problems
