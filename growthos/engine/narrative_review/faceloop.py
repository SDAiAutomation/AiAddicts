"""Point d'entrée Faceloop de Narrative Intelligence : un DRAPEAU et une démonstration HORS LIGNE. Rien d'autre.

    NARRATIVE_INTELLIGENCE_ENABLED=false   (valeur par défaut ; seules les valeurs exactes « true » et « 1 » activent)

Ce que le drapeau ouvre, et seulement cela : `ui_fixture()` fabrique, avec des fournisseurs FACTICES sous garde réseau hors ligne, une comparaison A/B de scripts synthétiques passée par la vraie chaîne
(adaptateur de snapshot, validation, décision serveur). Elle sert d'entrée locale à l'écran de test de growthos-web.

Ce que le drapeau n'ouvre PAS, quelle que soit sa valeur :
- aucun exécuteur, aucune fenêtre d'autorisation, aucun transport, aucun journal de campagne (`p0d/` n'est jamais importé ici) ;
- aucun appel à un fournisseur : l'activation d'un appel réel exige l'autorisation de campagne, le profil de modèle, le tokenizer validé, le contrôle réseau vivant et le journal canonique (voir `p0d/`) ;
- aucun branchement au worker, aux jobs, aux prompts de production, à Story Visual ou à Quiz.
Drapeau désactivé : `ui_fixture()` lève `NarrativeIntelligenceDisabled` et ne calcule rien.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import contract as c
from . import snapshot as snap
from .harness.offline import network_denied
from .providers import Budget, Prices, ProviderResult
from .reviewer import Caller, review

FLAG = "NARRATIVE_INTELLIGENCE_ENABLED"
FIXTURE_SCHEMA = "narrative-ui-fixture:0.1"
_TRUE = {"true", "1"}


class NarrativeIntelligenceDisabled(RuntimeError):
    def __init__(self):
        super().__init__(f"{FLAG} is not enabled (default: disabled): Narrative Intelligence is inert")


def is_enabled(env=None) -> bool:
    """Désactivé par défaut. Absent, vide, « false », « 0 », « yes », « TRUE2 », etc. : désactivé. Seuls « true » et « 1 » (casse et espaces ignorés) activent."""
    value = (os.environ if env is None else env).get(FLAG, "")
    return isinstance(value, str) and value.strip().lower() in _TRUE


def require_enabled(env=None) -> None:
    if not is_enabled(env):
        raise NarrativeIntelligenceDisabled()


# --- scénarios de démonstration (textes SYNTHÉTIQUES, écrits pour cet écran de test ; aucun prompt, aucune donnée de production) ---------------------------------

def _script(title: str, *lines: str) -> dict:
    roles = ["hook"] + ["point"] * (len(lines) - 2) + ["cta"]
    return {"title": title, "blocks": [{"role": r, "text": t} for r, t in zip(roles, lines)]}


DEMO = [
    {"topic_id": "D1", "label": "La file sans raison",
     "A": {"script": _script("La file sans raison", "Une file grandit devant la boulangerie, personne ne sait pourquoi.", "Un homme demande enfin à celui qui le précède.", "La réponse est simple : on attend le pain de six heures.", "Et toi, tu ferais la queue ?")},
     "B": {"script": _script("La file sans raison", "Une histoire incroyable va vous surprendre.", "Un homme demande enfin à celui qui le précède.", "La réponse est simple : on attend le pain de six heures.", "Et toi, tu ferais la queue ?"),
           "findings": [("HOOK_GENERIC", 0, "Ouverture générique : la promesse n'est pas spécifique.", "Nommer la file et l'énigme dès la première phrase.")]}},
    {"topic_id": "D2", "label": "Le pont qui chante",
     "A": {"script": _script("Le pont qui chante", "Chaque nuit, le vieux pont chante et personne ne comprend.", "Une ingénieure mesure le vent dans les câbles.", "Elle découvre que les haubans vibrent à la même note.", "Tout s'arrête d'un coup, sans explication."),
           "findings": [("ENDING_UNEARNED", 3, "La fin arrête le récit sans conséquence tirée de la découverte.", "Relier la note des haubans à ce qui s'arrête.")]},
     "B": {"script": _script("Le pont qui chante", "Chaque nuit, le vieux pont chante et personne ne comprend.", "Une ingénieure mesure le vent dans les câbles.", "Elle découvre que les haubans vibrent à la même note.", "Elle les détend un peu : le pont se tait, et la ville dort.")}},
    {"topic_id": "D3", "label": "La lettre jamais postée",
     "A": {"script": _script("La lettre jamais postée", "Une lettre dort depuis trente ans dans un manteau.", "Sa propriétaire la retrouve en vidant une armoire.", "Elle hésite, puis la glisse enfin dans la boîte.", "Certaines lettres attendent leur moment."),
           "findings": [("TRANSITION_WEAK", 2, "Le passage entre la découverte et la décision est abrupt.", "Ajouter ce qui lui fait changer d'avis.")]},
     "B": {"script": _script("La lettre jamais postée", "Une lettre dort depuis trente ans dans un manteau.", "Sa propriétaire la retrouve en vidant une armoire.", "Elle reconnaît l'écriture de sa sœur, et sa colère tombe : elle la poste.", "Certaines lettres attendent leur moment.")}},
    {"topic_id": "D4", "label": "Le chat du quartier",
     "A": {"script": _script("Le chat du quartier", "Un chat gris attend chaque matin devant la boulangerie fermée.", "Un enfant lui laisse une miette, puis une autre.", "Au bout d'un mois, tout le quartier le nourrit.", "Qui adopte qui ?"),
           "partial": "clarity"},
     "B": {"script": _script("Le chat du quartier", "Un chat gris attend chaque matin devant la boulangerie fermée.", "Un enfant lui laisse une miette, puis une autre.", "Au bout d'un mois, tout le quartier le nourrit.", "Qui adopte qui ?")}},
    {"topic_id": "D5", "label": "L'horloge arrêtée",
     "A": {"script": _script("L'horloge arrêtée", "L'horloge de la gare s'est arrêtée à 4 h 10.", "Le chef de gare jure qu'elle a été réparée la veille.", "Personne ne l'a touchée depuis l'an dernier.", "Alors qui l'a arrêtée ?"),
           "findings": [("CAUSAL_CONTRADICTION", (1, 2), "Réparée la veille, puis intouchée depuis un an : les deux phrases s'excluent.", "Choisir une seule version de l'histoire de l'horloge.")]},
     "B": {"script": _script("L'horloge arrêtée", "L'horloge de la gare s'est arrêtée à 4 h 10.", "Le chef de gare jure qu'elle fonctionnait la veille au soir.", "Elle marque toujours l'heure du dernier train.", "Alors, qui a arrêté le temps ?"),
           "findings": [("ORAL_DENSITY", 2, "Phrase dense à l'oral : trop d'informations d'un souffle.", "Couper en deux phrases courtes.")]}},
]


def _anchor(snapshot: dict, block: int) -> dict:
    unit = next(u for u in snapshot["units"] if u["unit_id"] == f"block-{block + 1:04d}")
    return {"unit_id": unit["unit_id"], "quote": unit["text"][: min(len(unit["text"]), 40)], "occurrence": 0}


def _response(snapshot: dict, variant: dict) -> dict:
    ids = [u["unit_id"] for u in snapshot["units"]]
    coverage = []
    for dimension in snapshot["required_dimensions"]:
        partial = variant.get("partial") == dimension
        coverage.append({"dimension": dimension, "status": "partial" if partial else "evaluated",
                         "reason": "lecture partielle simulée" if partial else "lecture simulée complète", "inspected_unit_ids": ids[: max(1, len(ids) // 2)] if partial else ids})
    findings = []
    for index, (code, blocks, reason, suggestion) in enumerate(variant.get("findings", ()), start=1):
        dimension, severities = c.CODES[code]
        blocks = blocks if isinstance(blocks, tuple) else (blocks,)
        anchors = [_anchor(snapshot, b) for b in blocks]
        findings.append({"finding_id": f"f{index}", "code": code, "dimension": dimension, "severity": severities[0], "assessment": "established", "anchors": anchors,
                         "source_evidence": [], "inspected_unit_ids": sorted({a["unit_id"] for a in anchors}), "reason": reason, "suggestion": suggestion,
                         "repair_scope": "local_text"})
    return {"schema_version": c.SCHEMA_VERSION, "coverage": coverage, "claims": [], "findings": findings}


def _indicators(report: dict) -> dict:
    """Indicateur par dimension, DÉRIVÉ de la validation (pas une note de modèle) : ok / warning / blocker / not_evaluated."""
    result = {item["dimension"]: ("ok" if item["status"] == "evaluated" else "not_evaluated") for item in report["coverage"]}
    for found in report["findings"]:
        current = result.get(found["dimension"], "ok")
        result[found["dimension"]] = "blocker" if (found["severity"] == "blocker" or current == "blocker") else "warning"
    return result


def _variant(label: str, spec: dict) -> dict:
    snapshot = snap.from_standard(spec["script"], organization_id="fixture-org", account_id="fixture-account", truth_mode="fiction")
    response = _response(snapshot, spec)

    def provider(request):
        return ProviderResult(text=json.dumps(response), usage={"input": 1000, "output": 200}, latency_s=0.1)
    report = review(snapshot, provider, caller=Caller("fixture-org", "fixture-account"), budget=Budget(1.0), prices=Prices(1.0, 2.0, as_of="n/a", source="FIXTURE"), model="local-fixture")
    return {"variant": label, "title": spec["script"]["title"], "blocks": spec["script"]["blocks"], "analysis_status": report["analysis_status"], "decision": report["decision"],
            "reasons": report["reasons"], "can_auto_accept": report["can_auto_accept"], "error": report["error"], "limits": report["limits"],
            "findings": [{k: f[k] for k in ("code", "dimension", "severity", "assessment", "reason", "suggestion")} | {"quotes": [a["quote"] for a in f["anchors"]]} for f in report["findings"]],
            "coverage": [{"dimension": x["dimension"], "status": x["status"]} for x in report["coverage"]], "indicators": _indicators(report)}


RANK = {"accept": 0, "accept_with_notes": 1, "revise": 2, "review": 3}


def ui_fixture() -> dict:
    """Comparaison A/B locale, SYNTHÉTIQUE, produite hors ligne (garde réseau active). Lève `NarrativeIntelligenceDisabled` si le drapeau est éteint."""
    require_enabled()
    cases = []
    with network_denied():
        for demo in DEMO:
            a, b = _variant("A", demo["A"]), _variant("B", demo["B"])
            better = "tie" if RANK[a["decision"]] == RANK[b["decision"]] else ("A" if RANK[a["decision"]] < RANK[b["decision"]] else "B")
            cases.append({"topic_id": demo["topic_id"], "label": demo["label"], "A": a, "B": b, "preferred_by_decision": better})
    return {"schema": FIXTURE_SCHEMA, "kind": "LOCAL_SYNTHETIC_FIXTURE", "policy_version": c.POLICY_VERSION, "critic_version": c.CRITIC_VERSION,
            "notice": "Données synthétiques produites hors ligne par des fournisseurs factices. Aucun modèle n'a été appelé ; aucune de ces décisions n'a de valeur éditoriale réelle.",
            "cases": cases}


def export_ui_fixture(path) -> Path:
    path = Path(path)
    data = ui_fixture()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Exporte la fixture locale de l'écran de test A/B (drapeau requis, hors ligne).")
    parser.add_argument("--export", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(export_ui_fixture(args.export))
    except NarrativeIntelligenceDisabled as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
