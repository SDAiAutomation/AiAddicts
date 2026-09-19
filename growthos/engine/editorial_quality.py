"""Contrôles éditoriaux simples orientés rétention short-form."""
import re


_GENERIC_HOOKS = (
    "voici", "tu veux", "vous voulez", "dans cette vidéo", "aujourd'hui",
    "saviez-vous", "le savais-tu", "bonjour",
)
_CURIOSITY_MARKERS = (
    "erreur", "jamais", "pourquoi", "secret", "personne", "sans", "avant",
    "sauf", "mais", "pourtant", "évite", "arrête", "contraire",
)
_WORD_RE = re.compile(r"\b[\wÀ-ÿ'’-]+\b", re.UNICODE)
# Les "visual" sont toujours en français (consigne au générateur d'images).
_WIDE_SHOT_PREFIXES = ("plan large", "plan d'ensemble", "vue d'ensemble", "vue large", "panoramique")
_MAX_TITLE_CHARS = 60  # le prompt demande 50 ; marge avant de pénaliser


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.strip())


def analyze_script(script: dict) -> dict:
    """Retourne un score et des problèmes actionnables, sans appel externe."""
    blocks = script.get("blocks") or []
    hook = next((str(b.get("text") or "") for b in blocks if b.get("role") == "hook"), "")
    cta = str(script.get("cta") or next(
        (b.get("text") or "" for b in blocks if b.get("role") == "cta"), ""
    ))
    hook_words = _words(hook)
    cta_words = _words(cta)
    lowered = hook.lower()
    issues: list[str] = []
    score = 100

    if not hook:
        score -= 60
        issues.append("Aucun hook explicite.")
    else:
        if len(hook_words) < 5:
            score -= 15
            issues.append("Hook trop court pour installer une promesse claire.")
        elif len(hook_words) > 18:
            score -= 20
            issues.append(f"Hook trop long ({len(hook_words)} mots, cible : 5–18).")

        generic_start = next((p for p in _GENERIC_HOOKS if lowered.startswith(p)), None)
        has_number = bool(re.search(r"\d", hook))
        has_curiosity = any(marker in lowered for marker in _CURIOSITY_MARKERS)
        if generic_start and not (has_number or has_curiosity):
            score -= 20
            issues.append(f"Ouverture générique (« {generic_start} ») sans tension ni curiosité.")
        if not (has_number or has_curiosity or "?" in hook):
            score -= 10
            issues.append("Hook sans élément concret, question ou contraste identifiable.")

    hook_block = next((b for b in blocks if b.get("role") == "hook"), None)
    hook_visual = str((hook_block or {}).get("visual") or "").strip().lower()
    if hook_visual.startswith(_WIDE_SHOT_PREFIXES):
        # Le titre promet un élément précis ; ouvrir sur un plan de situation
        # (rue, décor) fait décrocher avant que la promesse n'apparaisse.
        score -= 10
        issues.append("Hook filmé en plan large : ouvrir sur un gros plan de l'élément promis par le titre.")

    title = str(script.get("title") or "").strip()
    if len(title) > _MAX_TITLE_CHARS:
        score -= 5
        issues.append(f"Titre de {len(title)} caractères (cible : {_MAX_TITLE_CHARS} maximum, lisible en entier sur mobile).")

    if len(cta_words) > 12:
        score -= 15
        issues.append(f"CTA trop long ({len(cta_words)} mots, cible : 12 maximum).")

    return {
        "score": max(score, 0),
        "issues": issues,
        "hookWords": len(hook_words),
        "ctaWords": len(cta_words),
    }
