"""Contrat du storyboard produit par le réalisateur (`director.py`) et du rapport de rendu.

Comme `engine/motion_graphics/schema.py`, la validation porte sur la STRUCTURE : elle renvoie la liste des problèmes
(vide = valide) au lieu de lever, pour que l'appelant puisse demander une correction ciblée au réalisateur.
"""
from __future__ import annotations

import re

STORYBOARD_VERSION = "explainer-storyboard:v1"
TRUTH_MODES = ("fact", "inspired", "fiction")
TRANSITIONS = ("dip", "cut")
MAX_PLANS = 12
_ID = re.compile(r"^[a-z][a-z0-9_]{0,23}$")


def validate_storyboard(sb: object, n_lines: int) -> list[str]:
    """`n_lines` : nombre de lignes de narration que les plans doivent couvrir, dans l'ordre, sans trou."""
    if not isinstance(sb, dict):
        return ["le storyboard doit être un objet JSON"]
    errors: list[str] = []
    if sb.get("version") != STORYBOARD_VERSION:
        errors.append(f"version doit valoir {STORYBOARD_VERSION}")
    if sb.get("truthMode") not in TRUTH_MODES:
        errors.append(f"truthMode doit être l'un de {TRUTH_MODES}")
    if not isinstance(sb.get("world"), dict) or not str((sb.get("world") or {}).get("metaphor", "")).strip():
        errors.append("world.metaphor est obligatoire (la métaphore visuelle principale)")
    plans = sb.get("plans")
    if not isinstance(plans, list) or not plans:
        return errors + ["plans doit être une liste non vide"]
    if len(plans) > MAX_PLANS:
        errors.append(f"{len(plans)} plans : le maximum est {MAX_PLANS}")
    seen_ids: set[str] = set()
    expected = 0
    for i, plan in enumerate(plans):
        tag = f"plans[{i}]"
        if not isinstance(plan, dict):
            errors.append(f"{tag} doit être un objet")
            continue
        pid = plan.get("id")
        if not isinstance(pid, str) or not _ID.match(pid):
            errors.append(f"{tag}.id invalide (minuscules, chiffres, _ ; 24 caractères max)")
        elif pid in seen_ids:
            errors.append(f"{tag}.id « {pid} » en double")
        else:
            seen_ids.add(pid)
        lines = plan.get("lines")
        if not (isinstance(lines, list) and lines and all(isinstance(n, int) and not isinstance(n, bool) for n in lines)):
            errors.append(f"{tag}.lines doit lister les indices de lignes de narration couverts")
        else:
            if lines != list(range(expected, expected + len(lines))):
                errors.append(f"{tag}.lines = {lines} : attendu {list(range(expected, expected + len(lines)))} (contigu, dans l'ordre)")
            expected = lines[-1] + 1
        for key in ("intent", "visual", "camera"):
            if not str(plan.get(key, "")).strip():
                errors.append(f"{tag}.{key} est obligatoire")
        anchors = plan.get("anchors", [])
        if not isinstance(anchors, list):
            errors.append(f"{tag}.anchors doit être une liste")
            anchors = []
        anchor_ids: set[str] = set()
        for j, anchor in enumerate(anchors):
            a_tag = f"{tag}.anchors[{j}]"
            if not isinstance(anchor, dict) or not _ID.match(str(anchor.get("id", ""))) or not str(anchor.get("text", "")).strip():
                errors.append(f"{a_tag} doit avoir un id (minuscules/chiffres/_) et un text (mot ou groupe de mots de la narration)")
                continue
            if anchor["id"] in anchor_ids:
                errors.append(f"{a_tag}.id « {anchor['id']} » en double dans le plan")
            anchor_ids.add(anchor["id"])
            if not isinstance(anchor.get("occurrence", 1), int) or anchor.get("occurrence", 1) < 1:
                errors.append(f"{a_tag}.occurrence doit être un entier >= 1")
        if plan.get("transitionOut", "dip") not in TRANSITIONS:
            errors.append(f"{tag}.transitionOut doit être l'un de {TRANSITIONS}")
        for k, claim in enumerate(plan.get("claims", []) or []):
            if not isinstance(claim, dict) or not str(claim.get("text", "")).strip() or claim.get("kind") not in ("mechanism", "figure"):
                errors.append(f"{tag}.claims[{k}] : text et kind (mechanism|figure) sont obligatoires")
            elif claim["kind"] == "figure" and not claim.get("source"):
                errors.append(f"{tag}.claims[{k}] : un chiffre sans source n'est pas admis — reformule sans chiffre")
    if expected != n_lines:
        errors.append(f"les plans couvrent {expected} ligne(s) de narration sur {n_lines}")
    return errors
