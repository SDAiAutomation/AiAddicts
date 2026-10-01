"""Contrôle SÉMANTIQUE d'une scène Motion Graphics (Phase 5.2).

`schema.validate_scene` ne vérifie que la STRUCTURE (la bonne forme, non vide). Il laisse donc passer des
scènes dont les données ne signifient rien pour un spectateur — vus en rendu réel : `$Saved`, `$growth over
time`, `example rate`, un graphique sans aucune valeur, un « YES / NO » vide, un « VS » sans options.

Règle générale : une scène à données (graphique, comparaison, formule…) n'est dessinée que si elle porte de
VRAIES données lisibles. Sinon on retombe sur une scène typographique sûre (`icon_text`) et on le RECORDE ;
le moteur n'invente JAMAIS une valeur manquante.

Séparation à retenir :
- données visibles (`displayValue`, `value` d'une ligne, libellés…) : ce que le spectateur lit — doit venir du script ;
- paramètres de mise en page / d'animation (`targetRatio`, `maxValue`, `emphasis`…) : ne sont JAMAIS affichés comme
  une donnée. (Le « 49 % » / « 58 % » observé venait de `targetRatio`, rendu en pourcentage par erreur.)

Aucun appel réseau, aucun LLM.
"""
from __future__ import annotations

import re

from . import display_text

_DIGIT = re.compile(r"\d")
# Texte de remplissage qui ne doit jamais atteindre l'écran.
_PLACEHOLDERS = (
    re.compile(r"\$[A-Za-z]"),                                   # $Saved, $Spent, $growth, $X
    re.compile(r"\b[XN]\s*%"),                                  # X%, N%
    re.compile(r"\b(?:placeholder|lorem ipsum|tbd)\b", re.I),
    re.compile(r"\[[^\]]*\]|\{[^}]*\}"),                       # [value] {value}
)
# Une valeur affichée qui n'est QUE le mot « exemple » (displayValue: "example", "example rate").
_BARE_EXAMPLE = re.compile(r"^\s*(?:an?\s+)?(?:example|sample)(?:\s+(?:rate|value|total|amount|number))?\s*$", re.I)


def _s(value: object) -> str:
    return str(value or "").strip()


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_placeholder(text: object) -> bool:
    t = _s(text)
    return bool(t) and (any(p.search(t) for p in _PLACEHOLDERS) or bool(_BARE_EXAMPLE.match(t)))


def _viewer_strings(scene: dict) -> list[str]:
    out = [_s(scene.get(k)) for k in ("title", "label", "displayValue", "displayText", "text", "emphasis")]
    for key in ("steps", "items", "terms"):
        if isinstance(scene.get(key), list):
            out.extend(_s(v) for v in scene[key])
    for row in scene.get("data") or []:
        if isinstance(row, dict):
            out.extend((_s(row.get("label")), _s(row.get("displayValue"))))
    for key in ("optionA", "optionB", "before", "after"):
        if isinstance(scene.get(key), dict):
            out.extend((_s(scene[key].get("label")), _s(scene[key].get("displayValue"))))
    return [t for t in out if t]


def _rows(scene: dict) -> list[dict]:
    return [r for r in (scene.get("data") or []) if isinstance(r, dict)]


def _row_has_quantity(row: dict) -> bool:
    return _is_number(row.get("value")) or bool(_DIGIT.search(_s(row.get("displayValue"))))


def semantic_issues(scene: object) -> list[dict]:
    """Problèmes sémantiques bloquants d'une scène (liste vide = utilisable). Chaque entrée : {code, message}."""
    if not isinstance(scene, dict):
        return []
    kind = scene.get("sceneType") or scene.get("type")
    issues: list[dict] = []

    def add(code: str, message: str) -> None:
        issues.append({"code": code, "message": message})

    if any(has_placeholder(t) for t in _viewer_strings(scene)):
        add("placeholder_text", "texte de remplissage visible ($Saved, example, [value]…)")

    rows = _rows(scene)
    if kind in ("bar_chart", "donut_chart"):
        values = [r.get("value") for r in rows]
        if len(rows) < 2 or not all(_is_number(v) for v in values):
            add("chart_missing_values", "un graphique exige au moins 2 lignes avec une valeur numérique chacune")
        elif not any(v > 0 for v in values):
            add("chart_missing_values", "toutes les valeurs du graphique sont nulles")
    elif kind in ("money_split", "compound_growth"):
        if (kind == "money_split" and len(rows) < 2) or not rows or not all(_row_has_quantity(r) for r in rows):
            add("rows_without_quantity", "chaque ligne exige une valeur numérique ou un montant affiché")
    elif kind == "comparison":
        for key in ("optionA", "optionB"):
            opt = scene.get(key) if isinstance(scene.get(key), dict) else {}
            if not _s(opt.get("label")) or not _s(opt.get("displayValue")):
                add("empty_comparison", f"{key} n'a pas de libellé ET de contenu affiché")
                break
    elif kind == "before_after":
        for key in ("before", "after"):
            opt = scene.get(key) if isinstance(scene.get(key), dict) else {}
            if not _s(opt.get("label")) or not _s(opt.get("displayValue")):
                add("empty_before_after", f"{key} n'a pas de libellé ET de valeur affichée")
                break
    elif kind == "progress_bar":
        ratio = scene.get("targetRatio")
        if not _is_number(ratio) or not 0 <= ratio <= 1:
            add("bad_ratio", "targetRatio doit être un nombre entre 0 et 1")
        if not _DIGIT.search(_s(scene.get("displayValue"))):
            add("progress_without_quantity", "une barre de progression exige une quantité affichée (un chiffre)")
    elif kind == "formula":
        terms = [_s(t) for t in scene.get("terms") or []]
        if len([t for t in terms if t]) < 2:
            add("formula_too_short", "une formule exige au moins 2 termes")
    elif kind == "big_number":
        if not _DIGIT.search(_s(scene.get("displayValue"))):
            add("big_number_without_number", "un grand nombre exige un chiffre dans displayValue")
    elif kind in ("timeline", "checklist"):
        key = "steps" if kind == "timeline" else "items"
        if len([t for t in scene.get(key) or [] if _s(t)]) < 2:
            add("list_too_short", f"{key} exige au moins 2 éléments")
    return issues


_FILLER_START = re.compile(
    r"^\s*(?:(?:for )?example|analogy|quick (?:note|analogy|detail)|short answer|concrete \w+|practical \w+|"
    r"so|and|but|now|then|first|second)\s*[,:.—–-]+\s*", re.IGNORECASE)
_CLAUSE_SPLIT = re.compile(r"[.,;:!?\u2014\u2013]+\s+|\s+[-\u2014\u2013]\s+")
_MAX_WORDS, _MAX_CHARS = 9, 52  # budget d'affichage d'un icon_text (display_text.BUDGETS["display_text"])


def display_phrase(text: object) -> str:
    """Une PHRASE COURTE COMPLÈTE tirée d'un texte long, jamais un fragment tronqué : la phrase entière si elle tient
    dans le budget d'affichage, sinon la meilleure proposition (de préférence celle qui porte un chiffre). Retourne ""
    si aucune proposition entière ne tient (l'appelant choisit alors une autre source). Aucun « … »."""
    sentence = " ".join(str(text or "").split())
    for sep in (". ", "? ", "! "):
        if sep in sentence:
            sentence = sentence.split(sep, 1)[0]
            break
    sentence = sentence.strip(" .;:!-\u2014")
    if not sentence:
        return ""
    fits = lambda t: 1 <= len(t.split()) <= _MAX_WORDS and len(t) <= _MAX_CHARS
    stripped = _FILLER_START.sub("", sentence).strip(" ,;:.-")
    if fits(stripped):
        return stripped
    clauses = [_FILLER_START.sub("", c).strip(" ,;:.-") for c in _CLAUSE_SPLIT.split(sentence)]
    usable = [c for c in clauses if c and fits(c) and len(c.split()) >= 2]
    numbered = [c for c in usable if _DIGIT.search(c)]
    pick = (numbered or usable or [""])[0]
    return pick


def _clean_label(value: object) -> str:
    return display_text.fit_budget(display_text.strip_directions(_s(value)), "label")


def _facts(scene: dict) -> list[tuple[str, str]]:
    """(libellé, valeur affichée) des éléments réellement lisibles d'une scène : valeur non vide, sans texte de remplissage."""
    out: list[tuple[str, str]] = []
    candidates: list[dict] = list(_rows(scene))
    for key in ("optionA", "optionB", "before", "after"):
        if isinstance(scene.get(key), dict):
            candidates.append(scene[key])
    for row in candidates:
        label, value = _s(row.get("label")), _s(row.get("displayValue"))
        if not value and _is_number(row.get("value")):
            value = f"{row['value']:,.0f}".replace(",", ",") if float(row["value"]).is_integer() else f"{row['value']:g}"
        if value and not has_placeholder(value) and not has_placeholder(label):
            out.append((label, value))
    return out


def fallback_scene(scene: object, narration: str) -> dict:
    """Scène de REPLI sûre pour une scène à données inutilisables, avec les types existants — jamais de valeur inventée :

    - une seule donnée chiffrée lisible              -> big_number
    - plusieurs faits lisibles sans série numérique   -> checklist
    - barre de progression avec une quantité visible  -> big_number
    - sinon                                           -> icon_text (titre propre, sinon courte phrase de la narration)
    """
    raw = scene if isinstance(scene, dict) else {}
    kind = raw.get("sceneType") or raw.get("type")
    title = _s(raw.get("title"))
    clean_title = title if title and not has_placeholder(title) else ""
    facts = _facts(raw)
    numeric = [f for f in facts if _DIGIT.search(f[1])]

    if kind == "progress_bar" and _DIGIT.search(_s(raw.get("displayValue"))) and not has_placeholder(raw.get("displayValue")):
        return {"sceneType": "big_number", "displayValue": _s(raw.get("displayValue")), **({"title": clean_title} if clean_title else {})}
    if kind in ("bar_chart", "donut_chart", "money_split", "compound_growth", "comparison", "before_after"):
        if len(numeric) == 1:
            label, value = numeric[0]
            return {"sceneType": "big_number", "displayValue": value, **({"title": _clean_label(label)} if _clean_label(label) else
                                                                      ({"title": clean_title} if clean_title else {}))}
        usable = [f for f in (numeric if len(numeric) >= 2 else facts) if f[0]]
        if len(usable) >= 2:
            return {"sceneType": "checklist", **({"title": clean_title} if clean_title else {}),
                    "items": [f"{label}: {value}"[:64] for label, value in usable[:5]]}
    text = ""
    if clean_title:
        text = display_text.fit_budget(display_text.strip_directions(clean_title), "display_text")
    if not text:
        for key in ("displayValue", "text", "displayText"):
            if _s(raw.get(key)) and not has_placeholder(raw.get(key)):
                text = display_phrase(raw.get(key))
                if text:
                    break
    if not text:
        text = display_phrase(narration)
    if not text:  # aucune proposition entière : les premiers mots, sans « … », plutôt qu'un fragment tronqué en plein mot
        text = " ".join(str(narration or "").split()[:6])
    return {"sceneType": "icon_text", "text": display_text.fit_budget(display_text.strip_directions(text), "display_text") or " "}


def fallback_text(scene: object, narration: str) -> str:
    """Compat : texte du repli `icon_text` (voir `fallback_scene`)."""
    out = fallback_scene(scene, narration)
    return str(out.get("text") or out.get("displayValue") or " ")
