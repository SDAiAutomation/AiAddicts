"""Contrôle qualité automatique d'une vidéo générée.

Signaux objectifs uniquement (durée, visuels, densité de sous-titres, fichier
final) — pas de jugement subjectif. Retourne un score 0-100 et la liste des
motifs de pénalité. Un score sous `PASS_THRESHOLD` fait passer le content_item
en `quality_check` (coup d'œil humain avant publication) au lieu de `video` ;
le happy path (score >= seuil) va direct à `video`, un seul clic pour publier.

Volontairement simple et sans dépendance : le but est d'attraper les ratés
évidents (voix off trop courte, scènes sans visuel, rendu vide), pas de noter
finement la qualité éditoriale.
"""
from pathlib import Path

PASS_THRESHOLD = 70
MIN_DURATION_S = 60.0  # aligné sur engine.assembler.MIN_MONETIZABLE_DURATION_S
_MIN_FINAL_BYTES = 200_000  # une vidéo verticale de 60s+ pèse toujours bien plus

# Fenêtre plausible de cadence des sous-titres (cues/seconde). ~3 mots/cue et
# ~150 mots/min de voix off -> ~0,8 cue/s en régime normal ; on tolère large.
_MIN_CUE_DENSITY = 0.15
_MAX_CUE_DENSITY = 1.2


def score_generation(metrics: dict, final_path: str) -> tuple[int, list[str]]:
    """`metrics` : dict produit par engine.assembler._generate (durée totale,
    nombre de blocs, blocs avec visuel, nombre de cues, visuels possibles ou
    non). `final_path` : chemin de la vidéo finale rendue."""
    score = 100
    flags: list[str] = []

    total_duration = float(metrics.get("total_duration") or 0.0)
    if total_duration < MIN_DURATION_S:
        score -= 30
        flags.append(
            f"Voix off de {total_duration:.0f}s (moins de 60s) : non éligible à la "
            f"monétisation TikTok. Allonge le script."
        )

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
