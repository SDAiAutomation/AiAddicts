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


def build_scene_prompt(
    texts: list[str],
    niche: str | None,
    character_prefix: str = "",
    aspect_ratio: str = "9:16",
    style_bible: dict | None = None,
) -> str:
    """`texts` : les `visual` (ou `text` en repli) des blocs regroupés dans
    cette scène. `character_prefix` : sortie de
    `image_character_bible.build_character_prefix`. `style_bible` : sortie de
    `image_style_bible.resolve_style_bible`, optionnelle — sans elle, le
    prompt conserve un style réaliste générique."""
    niche_part = f" Contexte : niche {niche.replace('-', ' ')}." if niche else ""
    combined = " ".join(t.strip() for t in texts)
    ratio_part = _RATIO_PHRASE.get(aspect_ratio, _RATIO_PHRASE["9:16"])
    prefix = character_prefix.strip()

    identity = prefix or "Aucun personnage récurrent défini."

    composition = ""
    avoid_part = ""
    if style_bible:
        rules = str(style_bible.get("composition_rules") or "").strip()
        if rules:
            composition = f" {rules}"
        avoid = style_bible.get("avoid") or []
        if avoid:
            avoid_part = " " + ", ".join(str(a) for a in avoid) + "."

    style = str(
        (style_bible or {}).get("consigne")
        or "Photo réaliste, style contenu réseaux sociaux."
    ).strip()
    return (
        "BRIEF VISUEL — respecte chaque section.\n"
        f"IDENTITÉ ET CONTINUITÉ : {identity}\n"
        f"MOMENT NARRATIF : {combined}{niche_part}\n"
        "ACTION : montre exactement ce moment avec une pose, une expression et une interaction "
        "spécifiques ; évite le portrait générique face caméra.\n"
        f"STYLE VERROUILLÉ : {style}\n"
        f"CADRAGE : {ratio_part}.{composition}\n"
        "LISIBILITÉ MOBILE : contraste net, hiérarchie visuelle simple, point focal évident dès "
        "la première seconde.\n"
        "CONTRAINTES : SANS AUCUN TEXTE, mot, chiffre, légende, sous-titre, logo ni filigrane "
        f"dans l'image.{avoid_part}"
    )
