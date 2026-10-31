"""Trois directions artistiques réutilisables. Données pures, versionnées ; consommées par le compilateur de prompt
(`visual_direction.py`, qui s'appuie sur `engine.image_prompt_builder`) et par la composition typographique (`overlay.py`).

Le texte n'est JAMAIS dessiné par le modèle d'image : la typographie est composée localement (`overlay.py`).
"""
from __future__ import annotations

ART_DIRECTION_VERSION = 1

_COMMON_AVOID = [
    "pas de texte, de lettres, de chiffres, de logo ni de filigrane",
    "pas de visage générique face caméra, pas de mains déformées",
    "pas de composition centrée symétrique par défaut, pas de scène surchargée",
    "pas d'esthétique stock photo ni de rendu plastique",
]

DIRECTIONS: dict[str, dict] = {
    "editorial_knowledge": {
        "id": "editorial_knowledge",
        "label": {"fr": "Éditorial savoir", "en": "Editorial knowledge"},
        "description": {
            "fr": "Illustration éditoriale claire pour expliquer une idée : formes franches, un seul point focal.",
            "en": "Clear editorial illustration to explain one idea: bold shapes, a single focal point.",
        },
        "consigne": (
            "illustration éditoriale contemporaine façon presse magazine, formes géométriques franches, aplats de "
            "couleur avec grain de papier discret, un seul sujet symbolique net, grandes zones de respiration"
        ),
        "palette": "crème chaud, bleu encre, un accent corail ou ocre ; 4 couleurs maximum par image",
        "lighting": "lumière douce et diffuse, ombres portées simples",
        "contrast": "contraste net entre sujet et fond",
        "texture": "grain papier léger",
        "composition_rules": (
            "Sujet principal dans le tiers supérieur ou central, 30 % de vide en bas pour le texte. "
            "Silhouette lisible en miniature."
        ),
        "swatches": {"background": "#F4EBDD", "ink": "#1F2A44", "accent": "#E4664A"},
        "typography": {"font": "Poppins-Bold", "text_color": "#FFFFFF", "scrim": "#0E1626", "placement": "bottom"},
        "default_transition": "crossfade",
        "default_camera": "push_in",
    },
    "cinematic_story": {
        "id": "cinematic_story",
        "label": {"fr": "Récit cinématographique illustré", "en": "Cinematic illustrated story"},
        "description": {
            "fr": "Peinture illustrée à l'ambiance de film : lumière dramatique, personnages expressifs.",
            "en": "Illustrated painting with a film mood: dramatic light, expressive characters.",
        },
        "consigne": (
            "illustration narrative peinte à la main, ambiance de film d'animation d'auteur, lumière dramatique "
            "directionnelle, profondeur de champ, personnages aux silhouettes fortes et aux expressions lisibles"
        ),
        "palette": "palette restreinte et cohérente d'une scène à l'autre : un ton dominant froid ou chaud, un contrepoint",
        "lighting": "éclairage cinématographique, source de lumière motivée, rim light",
        "contrast": "contraste cinématographique modéré",
        "texture": "texture de peinture, léger grain de film",
        "composition_rules": (
            "Cadrage cinématographique, règle des tiers, sujet décentré avec regard ou mouvement vers l'espace libre. "
            "Le bas du cadre reste calme pour le texte."
        ),
        "swatches": {"background": "#16131F", "ink": "#F2E9DC", "accent": "#E0A458"},
        "typography": {"font": "Poppins-Bold", "text_color": "#FFF8EC", "scrim": "#0B0912", "placement": "bottom"},
        "default_transition": "fade",
        "default_camera": "push_in",
    },
    "conceptual_metaphor": {
        "id": "conceptual_metaphor",
        "label": {"fr": "Métaphore visuelle", "en": "Visual metaphor"},
        "description": {
            "fr": "Image symbolique forte : un objet ou une scène insolite porte toute l'idée.",
            "en": "A strong symbolic image: one unusual object or scene carries the whole idea.",
        },
        "consigne": (
            "image conceptuelle surréaliste épurée, une métaphore visuelle unique et immédiatement lisible, échelle "
            "inattendue entre les objets, fond minimal en aplat dégradé, éclairage de studio théâtral"
        ),
        "palette": "deux teintes dominantes complémentaires et un neutre ; fond uni ou dégradé simple",
        "lighting": "éclairage théâtral, ombre longue expressive",
        "contrast": "contraste fort, silhouette découpée",
        "texture": "surfaces lisses, grain très fin",
        "composition_rules": (
            "Un seul objet-métaphore au premier plan, composition minimaliste, horizon bas. "
            "Aucune scène secondaire. Zone basse libre pour le texte."
        ),
        "swatches": {"background": "#1B3A4B", "ink": "#F6F1E9", "accent": "#F2B134"},
        "typography": {"font": "Poppins-Bold", "text_color": "#FFFFFF", "scrim": "#0A1820", "placement": "bottom"},
        "default_transition": "crossfade",
        "default_camera": "pull_out",
    },
}


def get_direction(direction_id: str) -> dict:
    try:
        return DIRECTIONS[direction_id]
    except KeyError:
        raise ValueError(f"direction artistique inconnue : {direction_id!r} (attendu {tuple(DIRECTIONS)})") from None


def style_bible(direction_id: str) -> dict:
    """Dict compatible avec `engine.image_prompt_builder.build_scene_prompt(style_bible=...)` (même clés que
    `image_style_bible.resolve_style_bible`), pour réutiliser le constructeur de prompt existant tel quel."""
    d = get_direction(direction_id)
    return {
        "visual_style_id": d["id"],
        "consigne": d["consigne"],
        "avoid": list(_COMMON_AVOID),
        "composition_rules": d["composition_rules"],
        "version": ART_DIRECTION_VERSION,
        "palette": d["palette"],
        "contrast": d["contrast"],
        "texture": d["texture"],
    }
