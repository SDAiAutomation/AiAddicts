"""Traitements de style déterministes, locaux (Pillow, aucun appel IA) qui
donnent à `comic_book` et `gta_loading` (Game Loading Screen) une identité
visuelle réelle au-delà d'un simple prompt d'image différent — Phase 3.

Opère sur une image de scène DÉJÀ générée (fraîche ou réutilisée dans le
même bloc receveur, voir Phase 2.6) ; la sortie est un `.jpg` de même rôle
qui repart tel quel dans le pipeline Ken Burns / rendu existant
(`engine/video.py`, jamais modifié par ce module) — une couche de
compositing, jamais un second assembleur.

Voir `comic.py` / `game_art.py` pour le détail de chaque traitement."""
from __future__ import annotations

from . import comic, game_art

TREATMENTS = {
    "comic_book": comic,
    "gta_loading": game_art,
}


def has_treatment(visual_style_id: str | None) -> bool:
    return visual_style_id in TREATMENTS


def apply_treatment(
    visual_style_id: str, source_path: str, out_path: str, shot_type: str | None, visual_purpose: str | None
) -> dict | None:
    """`None` si ce style n'a pas de traitement (l'appelant garde l'image
    d'origine). Peut lever une exception (I/O, Pillow) — voir
    `engine.visuals._apply_style_treatments` pour le repli sur l'image non
    traitée : un échec de filtre graphique ne doit jamais casser le rendu."""
    module = TREATMENTS.get(visual_style_id)
    if not module:
        return None
    return module.apply(source_path, out_path, shot_type, visual_purpose)
