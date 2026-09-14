"""Assemble le prompt final d'une scène à partir de : la fiche personnage
(`engine.image_character_bible`), la Style Bible (`engine.image_style_bible`)
et le texte de la scène elle-même. Déterministe et pur — aucun appel réseau,
directement testable.

Déplacé depuis `engine/visuals.py` (`_scene_prompt`) : le comportement par
défaut (sans `style_bible`) est identique à l'ancien, voir
`tests/test_image_prompt_builder.py`.
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
    prompt est identique à l'ancien `visuals._scene_prompt` (rétro-compat)."""
    niche_part = f" Contexte : niche {niche.replace('-', ' ')}." if niche else ""
    combined = " ".join(t.strip() for t in texts)
    ratio_part = _RATIO_PHRASE.get(aspect_ratio, _RATIO_PHRASE["9:16"])
    prefix = character_prefix.strip()

    if prefix:
        # Chaque scène est une génération texte indépendante : la pose/le
        # décor/l'action suivent donc déjà naturellement le texte de CETTE
        # scène. On le rappelle explicitement pour éviter que le modèle ne
        # retombe sur une pose de portrait générique malgré la description
        # figée du personnage.
        header = (
            prefix + "\n"
            "Illustre la posture, l'angle de caméra, le décor et l'action précis de la scène "
            "décrite plus bas — pas un simple portrait générique du personnage.\n"
        )
    else:
        header = "Photo réaliste, style contenu réseaux sociaux. "

    composition = ""
    avoid_part = ""
    if style_bible:
        rules = str(style_bible.get("composition_rules") or "").strip()
        if rules:
            composition = f" {rules}"
        avoid = style_bible.get("avoid") or []
        if avoid:
            avoid_part = " " + ", ".join(str(a) for a in avoid) + "."

    return (
        f"{header}"
        f"{ratio_part}.{composition} "
        f"SANS AUCUN TEXTE, mot, chiffre, légende, sous-titre, logo ni filigrane dans l'image."
        f"{avoid_part}"
        f"{niche_part}\n"
        f"Scène : {combined}"
    )
