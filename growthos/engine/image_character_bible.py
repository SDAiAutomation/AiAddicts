"""Character Bible Faceloop : fiche personnage textuelle, CONDITIONNELLE par
scène ("si {name} apparaît dans cette scène..."), injectée en tête de chaque
prompt de scène — voir `engine/image_prompt_builder.build_scene_prompt`.

Pourquoi textuel et pas une image de référence : testé et abandonné (voir
`engine/visuals.py`, commit `eae9d7c`) — dériver les scènes suivantes d'une
image de référence via `/v1/images/edits` garde le personnage mais fige la
pose et le cadrage d'une scène à l'autre. Une image de référence par
personnage (plutôt qu'un enchaînement scène→scène) reste une piste future
raisonnable (voir `engine/openai_images.edit_image`, déjà prêt à accepter une
image de référence pour un usage différent : la correction ciblée), mais
n'est pas branchée ici tant qu'elle n'a pas été vérifiée en situation réelle.

Déplacé depuis `engine/visuals.py` sans changement de comportement — voir
`tests/test_image_character_bible.py` (relocalisé depuis `test_visuals.py`).
"""
from . import image_style_bible


def build_character_prefix(characters: list[dict] | None, visual_style: str | None) -> str:
    """Bloc de texte figé, identique pour toutes les scènes d'une vidéo :
    description physique de chaque personnage (CONDITIONNELLE : seulement
    s'il apparaît dans la scène) + contrainte négative + style graphique.
    Concaténé en tête de chaque prompt de scène.

    La condition est volontaire : beaucoup de scènes sont des gros plans
    d'objet, des POV ou des plans larges de décor sans aucun personnage — une
    description non conditionnelle pousserait le modèle à insérer le
    personnage même sur ces plans-là.

    `characters` : liste de dicts `{name, description, negative?}` venant de
    `script["characters"]`. Entrées incomplètes ignorées. Retourne '' si
    rien d'exploitable (le prompt retombe alors sur son style générique).

    `visual_style` : id de style connu OU phrase déjà résolue (les deux
    fonctionnent, `image_style_bible.style_consigne_for` est idempotent sur
    du texte libre) — voir `image_style_bible` pour le catalogue."""
    lines: list[str] = []
    has_any = False
    for character in characters or []:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name", "")).strip()
        description = str(character.get("description", "")).strip()
        if not name or not description:
            continue
        has_any = True
        sentence = f"Si {name} apparaît dans cette scène, son apparence est TOUJOURS la même : {name} est {description}."
        negative = str(character.get("negative", "")).strip()
        if negative:
            sentence += f" Ne jamais représenter {name} autrement : {negative}."
        lines.append(sentence)

    if has_any:
        lines.append(
            "Si aucun de ces personnages n'apparaît dans cette scène précise (plan sur un "
            "objet, un décor, un point de vue subjectif...), ignore ces descriptions et "
            "n'inclus personne : illustre uniquement ce que la scène décrit."
        )

    style = image_style_bible.style_consigne_for(visual_style)
    if style:
        lines.append(f"Style graphique identique pour toute la vidéo : {style}.")

    return " ".join(lines)
