"""Assemble le prompt final d'une scène à partir de : la fiche personnage
(`engine.image_character_bible`), la Style Bible (`engine.image_style_bible`)
et le texte de la scène elle-même. Déterministe et pur — aucun appel réseau,
directement testable.

Le brief est structuré en identité, moment, action, style, cadrage et
contraintes pour améliorer l'adhérence du modèle et stabiliser chaque scène.
"""

_RATIO_PHRASE = {
    "9:16": "cadrage vertical plein cadre (format 9:16, TikTok/Reels/Shorts)",
    "1:1": "cadrage carré plein cadre (format 1:1)",
    "16:9": "cadrage horizontal plein cadre (format 16:9)",
}

# Phase 1 (shot planning) : traduit un `shotType` structuré (voir
# engine/shot_planning.py) en consigne de cadrage explicite pour le
# générateur d'images — remplace la seule confiance dans le "visual" en
# prose pour obtenir le cadrage réellement demandé.
_SHOT_TYPE_PHRASE = {
    "wide": "Plan large : cadre l'ensemble du décor autour du sujet, le sujet reste petit dans le cadre.",
    "medium": "Plan moyen : cadre le sujet de la taille à la tête environ, avec du contexte visible autour.",
    "close_up": "Gros plan : cadre serré sur le visage ou un détail précis, arrière-plan flou ou effacé.",
    "insert": (
        "Plan d'insert : cadre UNIQUEMENT un objet, un écran ou un détail précis, sans aucun visage ni "
        "personnage entier dans le cadre."
    ),
    "pov": (
        "Plan subjectif (POV) : cadre à travers les yeux du personnage, ne montre jamais son visage ni son corps."
    ),
}


def build_scene_prompt(
    texts: list[str],
    niche: str | None,
    character_prefix: str = "",
    aspect_ratio: str = "9:16",
    style_bible: dict | None = None,
    shot_type: str | None = None,
) -> str:
    """`texts` : les `visual` (ou `text` en repli) des blocs regroupés dans
    cette scène. `character_prefix` : sortie de
    `image_character_bible.build_character_prefix`. `style_bible` : sortie de
    `image_style_bible.resolve_style_bible`, optionnelle — sans elle, le
    prompt conserve un style réaliste générique. `shot_type` : `shotType`
    structuré du premier bloc de la scène (voir engine/shot_planning.py),
    optionnel — absent ou inconnu, le cadrage reste dicté par `texts` et la
    Style Bible comme avant (rétro-compatible)."""
    niche_part = f" Contexte : niche {niche.replace('-', ' ')}." if niche else ""
    combined = " ".join(t.strip() for t in texts)
    ratio_part = _RATIO_PHRASE.get(aspect_ratio, _RATIO_PHRASE["9:16"])
    shot_part = f" {_SHOT_TYPE_PHRASE[shot_type]}" if shot_type in _SHOT_TYPE_PHRASE else ""
    prefix = character_prefix.strip()

    identity = prefix or "Aucun personnage récurrent défini."

    composition = ""
    avoid_part = ""
    if style_bible:
        rules = str(style_bible.get("composition_rules") or "").strip()
        if rules and aspect_ratio == "9:16":
            composition = f" {rules}"
        avoid = style_bible.get("avoid") or []
        if avoid:
            avoid_part = " " + ", ".join(str(a) for a in avoid) + "."

    style = str(
        (style_bible or {}).get("consigne")
        or "Photo réaliste, style contenu réseaux sociaux."
    ).strip()

    # StyleIdentity (Phase 2) : précision courte, seulement si ce style en
    # définit une — absente pour la plupart des styles, comportement
    # identique à avant cette phase. N'allonge jamais le prompt de plus
    # qu'une clause courte par champ.
    identity_bits = [
        str((style_bible or {}).get(field)).strip()
        for field in ("palette", "contrast", "texture")
        if (style_bible or {}).get(field)
    ]
    identity_part = f" ({', '.join(identity_bits)})" if identity_bits else ""

    return (
        "BRIEF VISUEL — respecte chaque section.\n"
        f"IDENTITÉ ET CONTINUITÉ : {identity}\n"
        f"MOMENT NARRATIF : {combined}{niche_part}\n"
        "ACTION : montre exactement le sujet, l'objet et le geste décrits dans le moment narratif. "
        "Pour un plan d'objet, de décor ou en point de vue subjectif, n'ajoute ni visage ni personnage. "
        "Si une personne est explicitement présente, montre sa pose et son interaction précises ; "
        "évite le portrait générique face caméra.\n"
        f"STYLE VERROUILLÉ : {style}{identity_part}\n"
        f"CADRAGE : {ratio_part}.{shot_part}{composition}\n"
        "LISIBILITÉ MOBILE : contraste net, hiérarchie visuelle simple, point focal évident dès "
        "la première seconde.\n"
        "CONTRAINTES : SANS AUCUN TEXTE, mot, chiffre, légende, sous-titre, logo ni filigrane "
        f"dans l'image.{avoid_part}"
    )
