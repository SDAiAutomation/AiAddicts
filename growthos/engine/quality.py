"""Contrôle qualité automatique d'une vidéo générée.

Signaux techniques et éditoriaux (objectif, hook, rythme visuel, sous-titres,
fichier final). Retourne un score 0-100 et la liste des
motifs de pénalité. Un score sous `PASS_THRESHOLD` fait passer le content_item
en `quality_check` (coup d'œil humain avant publication) au lieu de `video` ;
le happy path (score >= seuil) va direct à `video`, un seul clic pour publier.

Volontairement déterministe et sans dépendance externe : le but est d'attraper
les ratés évidents avant publication, puis de laisser les métriques réelles
alimenter une future boucle d'apprentissage.
"""
from pathlib import Path

PASS_THRESHOLD = 70
MIN_MONETIZATION_DURATION_S = 60.0
MIN_REACH_DURATION_S = 8.0
MAX_REACH_DURATION_S = 60.0
MAX_HOOK_DURATION_S = 4.0
MAX_SHOT_DURATION_S = 3.2
_MIN_FINAL_BYTES = 200_000  # une vidéo verticale de 60s+ pèse toujours bien plus

# Fenêtre plausible de cadence des sous-titres (cues/seconde). 3 mots/cue
# (engine.captions._WORDS_PER_CUE) et une voix off synthétique mesurée à
# ~200-210 mots/min -> ~1,15 cue/s en régime normal, ~1,3 sur un passage
# rapide. Le plafond attrape un timing vraiment cassé (mots collés), pas un
# débit soutenu normal.
_MIN_CUE_DENSITY = 0.15
_MAX_CUE_DENSITY = 1.6


def score_generation(metrics: dict, final_path: str) -> tuple[int, list[str]]:
    """`metrics` : dict produit par engine.assembler._generate (durée totale,
    nombre de blocs, blocs avec visuel, nombre de cues, visuels possibles ou
    non). `final_path` : chemin de la vidéo finale rendue."""
    score = 100
    flags: list[str] = []

    total_duration = float(metrics.get("total_duration") or 0.0)
    content_goal = metrics.get("content_goal") or "reach"
    if content_goal == "monetization" and total_duration < MIN_MONETIZATION_DURATION_S:
        score -= 30
        flags.append(
            f"Voix off de {total_duration:.0f}s (moins de 60s) : non éligible à la "
            "monétisation TikTok."
        )
    elif content_goal == "reach":
        if total_duration < MIN_REACH_DURATION_S:
            score -= 20
            flags.append(f"Vidéo très courte ({total_duration:.0f}s) : promesse probablement incomplète.")
        elif total_duration > MAX_REACH_DURATION_S:
            score -= 15
            flags.append(
                f"Vidéo longue pour un objectif de portée ({total_duration:.0f}s) : "
                "resserrer le script ou choisir content_goal=monetization."
            )

    hook_duration = metrics.get("hook_duration")
    if hook_duration is not None and float(hook_duration) > MAX_HOOK_DURATION_S:
        score -= 15
        flags.append(
            f"Hook de {float(hook_duration):.1f}s (cible : 4s maximum) : révéler la promesse plus vite."
        )

    max_shot_duration = float(metrics.get("max_shot_duration") or 0.0)
    if max_shot_duration > MAX_SHOT_DURATION_S:
        score -= 15
        flags.append(
            f"Plan visuel de {max_shot_duration:.1f}s (cible : 3s maximum) : rythme trop lent."
        )

    editorial = metrics.get("editorial") or {}
    editorial_score = editorial.get("score")
    if editorial_score is not None and int(editorial_score) < 85:
        # Un hook faible suffit à tuer la distribution, même si le fichier est
        # techniquement parfait. La pénalité fait passer ce cas sous le seuil
        # de publication automatique.
        score -= 35
        issues = editorial.get("issues") or []
        detail = f" {issues[0]}" if issues else ""
        flags.append(f"Qualité éditoriale faible ({editorial_score}/100).{detail}")

    n_blocks = int(metrics.get("n_blocks") or 0)
    blocks_with_image = int(metrics.get("blocks_with_image") or 0)
    if metrics.get("visuals_possible") and n_blocks and blocks_with_image < n_blocks:
        score -= 20
        missing = n_blocks - blocks_with_image
        flags.append(
            f"{missing} bloc(s) sur {n_blocks} sans visuel (fond uni) : échec de "
            f"génération d'image ou clé absente pour ces scènes."
        )

    n_cues = int(metrics.get("n_cues") or 0)
    if total_duration > 0 and n_cues > 0:
        density = n_cues / total_duration
        if density < _MIN_CUE_DENSITY or density > _MAX_CUE_DENSITY:
            score -= 10
            flags.append(
                f"Densité de sous-titres inhabituelle ({density:.2f} cue/s) — "
                f"timing de la voix off à vérifier."
            )

    path = Path(final_path)
    if not path.exists() or path.stat().st_size < _MIN_FINAL_BYTES:
        score -= 40
        flags.append("Fichier vidéo final absent ou anormalement petit — rendu suspect.")

    return max(score, 0), flags
