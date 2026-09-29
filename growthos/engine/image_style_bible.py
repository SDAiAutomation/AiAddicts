"""Style Bible Faceloop : identité visuelle résolue UNE FOIS par script et
réutilisée sur toutes les scènes — clé de la cohérence visuelle (même esprit
que `image_character_bible.build_character_prefix`, l'autre moitié du
préfixe historiquement appelé `character_prefix`).

Le catalogue `_VISUAL_STYLE_PROMPTS` (styles choisis dans l'UI Faceloop) est
repris tel quel depuis `engine/visuals.py` — DOIT rester aligné avec
`VISUAL_STYLES` de growthos-web (`content-config.tsx`) : Faceloop écrit de
toute façon la phrase déjà résolue dans `visual_style_prompt`, ceci n'est que
le repli / le chemin CLI.

Ce qui est NOUVEAU ici (par rapport à l'ancien `_style_consigne` seul) :
une avoid-list + des règles de composition portrait, appliquées à TOUS les
styles (pas seulement au style réaliste) — voir `resolve_style_bible`.
"""

IMAGE_PROMPT_VERSION = "3.1.0"
STYLE_BIBLE_VERSION = "1.1.0"

_VISUAL_STYLE_PROMPTS = {
    "flat_color": "",  # "fond uni + texte" : pas de visuel IA, géré par video.py
    "motion_graphics": "",  # rendu local (engine/motion_graphics/), pas de visuel IA
    "stock_footage": "photographie réaliste style contenu réseaux sociaux, lumière naturelle",
    "minimal_slides": "illustration minimaliste, aplats de couleur, formes géométriques simples",
    "pixar_3d": (
        "rendu 3D façon film d'animation Pixar, personnages expressifs aux formes "
        "arrondies, éclairage doux, textures léchées, couleurs chaudes"
    ),
    "anime": (
        "style anime japonais, cel-shading, traits nets, grands yeux expressifs, "
        "arrière-plans peints, couleurs saturées"
    ),
    "comic_book": (
        "style bande dessinée, encrage noir marqué, aplats de couleur, trames, "
        "ombres franches"
    ),
    "storybook": (
        "illustration album jeunesse, aquarelle et crayon, couleurs douces et pastel, "
        "formes arrondies, contours doux"
    ),
    "gta_loading": (
        "illustration façon écran de chargement de jeu vidéo type GTA, semi-réaliste "
        "stylisé, contours nets, ombrage cell, ambiance cinématique contrastée"
    ),
    "cinematic_real": (
        "photo cinématique réaliste, objectif 35mm, faible profondeur de champ, "
        "étalonnage type film, lumière naturelle"
    ),
    # rétro-compat : ancien id
    "anime_3d": (
        "rendu 3D façon film d'animation, couleurs vives, personnages aux formes "
        "arrondies, rendu doux et léché"
    ),
}

# Appliquée à TOUS les styles (pas seulement cinematic_real) : ce sont des
# défauts de qualité/propreté d'image, pas une identité graphique. Étend le
# "SANS AUCUN TEXTE..." déjà présent dans le prompt de scène (voir
# image_prompt_builder.build_scene_prompt).
_DEFAULT_AVOID = [
    "logo, filigrane, watermark",
    "personnes dupliquées",
    "membres en trop ou manquants, mains ou doigts déformés",
    "anatomie distordue",
    "HDR excessif, couleurs sursaturées",
]

_COMPOSITION_RULES = (
    "Cadrage vertical : sujet principal dans la zone centrale sûre, jamais coupé sur "
    "les bords du cadre. Aucun détail de visage critique dans les 10% extrêmes du "
    "cadre. Laisse de l'espace visuel utilisable en bas de l'image pour des "
    "sous-titres (rien d'important à cet endroit)."
)

# StyleIdentity (Phase 2) : EXTENSION minimale de la Style Bible existante,
# pas un nouveau système. Seuls les champs réellement consommés cette
# phase-ci : `motion_profile` (engine/motion_profiles.py, remplace le
# `block_index % 6` générique dans engine/video.py), `transition`
# ("cut"/"fade", voir engine/video.py::_render_block_clip — "fade" reste un
# fondu à l'entrée/sortie de CHAQUE plan, jamais un vrai fondu enchaîné entre
# deux plans, qui exigerait de remplacer le concat demuxer par un graphe de
# filtres — risque jugé trop élevé pour cette phase, voir le rapport)
# et `palette`/`contrast`/`texture` (courte précision ajoutée au prompt
# d'image, voir image_prompt_builder.build_scene_prompt). Un id absent de ce
# dict reçoit le profil par défaut et aucune précision de prompt
# supplémentaire — comportement identique à avant cette phase.
_STYLE_IDENTITY: dict[str, dict] = {
    "flat_color": {"motion_profile": "kinetic"},
    "motion_graphics": {"motion_profile": "kinetic"},
    "stock_footage": {"motion_profile": "none"},
    "minimal_slides": {"motion_profile": "gentle"},
    "pixar_3d": {"motion_profile": "cinematic"},
    "cinematic_3d": {"motion_profile": "cinematic"},  # id futur éventuel, voir README
    "anime": {"motion_profile": "energetic"},
    "comic_book": {
        "motion_profile": "comic",
        "contrast": "contraste marqué, ombres franches et aplats nets, façon encrage de bande dessinée",
    },
    "storybook": {
        "motion_profile": "gentle",
        "transition": "fade",
        "palette": "couleurs douces et pastel",
        "texture": "grain aquarelle léger",
    },
    "gta_loading": {"motion_profile": "energetic"},
    "game_loading": {"motion_profile": "energetic"},  # id futur éventuel, voir README
    "cinematic_real": {
        "motion_profile": "cinematic",
        "contrast": "contraste cinématographique modéré",
        "texture": "léger grain de film",
    },
    "anime_3d": {"motion_profile": "cinematic"},  # rétro-compat : ancien id
}


def style_consigne_for(visual_style: str | None) -> str:
    """Traduit un id de style connu en phrase de consigne ; une phrase libre
    est renvoyée telle quelle ; vide -> ''. Utilisé à la fois pour résoudre
    `resolve_style_bible` et par `image_character_bible.build_character_prefix`
    (rétro-compat : ce module acceptait déjà un id OU du texte déjà résolu,
    idempotent dans les deux cas — voir les tests)."""
    if not visual_style:
        return ""
    key = visual_style.strip()
    if key in _VISUAL_STYLE_PROMPTS:
        return _VISUAL_STYLE_PROMPTS[key]
    return key


def motion_profile_for(visual_style: str | None) -> str | None:
    """Le `motion_profile` de StyleIdentity pour cet id, ou `None` si inconnu
    — l'appelant (engine/motion_profiles.py) applique alors son propre
    défaut. Ne lève jamais, ne devine jamais depuis une phrase libre (une
    phrase de style CLI non cataloguée n'a pas de profil de mouvement connu)."""
    identity = _STYLE_IDENTITY.get((visual_style or "").strip())
    return identity.get("motion_profile") if identity else None


def resolve_style_bible(visual_style: str | None, visual_style_prompt: str | None = None) -> dict:
    """Résolu une fois par script (voir `visuals.fetch_block_images`), pas par
    scène — c'est la clé de la cohérence de style. `visual_style_prompt`
    (phrase déjà résolue côté growthos-web) l'emporte toujours sur
    `visual_style` (id ou phrase libre, chemin CLI).

    Inclut StyleIdentity (Phase 2) : `motion_profile`, `transition`
    ("cut" par défaut) et les précisions de prompt optionnelles
    `palette`/`contrast`/`texture` (`None` si non définies pour ce style —
    voir `image_prompt_builder.build_scene_prompt`, qui les ignore alors
    silencieusement, comportement identique à avant cette phase)."""
    from . import motion_profiles

    style_id = (visual_style or "").strip()
    consigne = (visual_style_prompt or "").strip() or style_consigne_for(style_id)
    identity = _STYLE_IDENTITY.get(style_id, {})
    return {
        "visual_style_id": style_id,
        "consigne": consigne,
        "avoid": list(_DEFAULT_AVOID),
        "composition_rules": _COMPOSITION_RULES,
        "version": STYLE_BIBLE_VERSION,
        "prompt_version": IMAGE_PROMPT_VERSION,
        "motion_profile": identity.get("motion_profile") or motion_profiles.DEFAULT_PROFILE,
        "transition": identity.get("transition") or "cut",
        "palette": identity.get("palette"),
        "contrast": identity.get("contrast"),
        "texture": identity.get("texture"),
    }
