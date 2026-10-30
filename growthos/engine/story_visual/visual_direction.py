"""Visual Direction -> prompt d'image. Réutilise `image_character_bible` et `image_prompt_builder` (aucun second constructeur).

Le plan porte déjà, par scène, la `visual_direction` (comprendre / ressentir / métaphore / essentiel / omettre /
continuité) produite AVANT le prompt. Ici : (1) fiche d'identité des personnages -> texte verrouillé, (2) assemblage
du prompt final, (3) politique d'usage d'une image de référence (coûteuse, non prouvée : désactivée par défaut).
"""
from __future__ import annotations

from .. import image_character_bible, image_prompt_builder
from . import art_directions


def character_cards(plan: dict) -> list[dict]:
    """Contrat d'identité -> entrées `{name, description, negative}` du Character Bible existant."""
    cards = []
    for c in plan.get("characters", []):
        description = (
            f"{c['appearance'].rstrip('.')}. Proportions : {c['proportions'].rstrip('.')}. "
            f"Tenue : {c['clothing'].rstrip('.')}. Palette : {c['palette'].rstrip('.')}. "
            f"Signe distinctif : {c['distinctive'].rstrip('.')}"
        )
        if c.get("environment"):
            description += f". Environnement habituel : {c['environment'].rstrip('.')}"
        cards.append({"name": c["name"], "description": description,
                      "negative": c.get("negative", "changer de tenue, de proportions ou de palette")})
    return cards


def _scene_characters(plan: dict, scene: dict) -> list[dict]:
    present = set(scene.get("characters", []))
    by_id = {c["id"]: card for c, card in zip(plan.get("characters", []), character_cards(plan))}
    return [by_id[cid] for cid in by_id if cid in present]


def expression_for(scene: dict) -> str:
    return f"Expression et posture : {scene['emotional_tone']}."


FRAMING_RULES = (
    "CADRAGE SÛR (9:16) : l'image sera recadrée au centre en 9:16, on perd environ 7 % de chaque côté. Garde TOUS les sujets, visages et "
    "mains dans la bande centrale, rien d'essentiel contre les bords gauche et droit. Le quart inférieur du cadre reste CALME et sombre "
    "(aplat, table, sol), sans visage, sans main, sans détail : il porte la typographie."
)


def identity_block(plan: dict, scene: dict) -> str:
    """Bloc d'identité placé EN TÊTE du prompt, car un détail demandé en fin de prompt dérive d'une image à l'autre (pilote mesuré :
    signe distinctif, bas de tenue, coiffure et âge apparent variaient). Vide s'il n'y a aucun personnage dans la scène."""
    present = set(scene.get("characters", []))
    parts = []
    for c in plan.get("characters", []):
        if c["id"] not in present:
            continue
        parts.append(
            f"IDENTITÉ DE {c['name'].upper()} — IDENTIQUE DANS TOUTES LES IMAGES. SIGNE DISTINCTIF OBLIGATOIRE, de la même forme et du même côté : "
            f"{c['distinctive'].rstrip('.')}. TENUE COMPLÈTE, du haut en bas, sans jamais en changer : {c['clothing'].rstrip('.')}. "
            f"Visage et coiffure : {c['appearance'].rstrip('.')}, même âge apparent, même coiffure à chaque image. "
            f"Proportions : {c['proportions'].rstrip('.')}. Palette : {c['palette'].rstrip('.')}.")
    return " ".join(parts)


def build_image_prompt(plan: dict, scene_index: int) -> str:
    """Prompt déterministe d'une scène. N'inclut que les personnages PRÉSENTS dans la scène (sinon le modèle les
    ajoute partout), mais avec la même fiche d'identité dans toutes les scènes où ils apparaissent."""
    scenes = plan["scenes"]
    scene = scenes[scene_index]
    d = scene["visual_direction"]
    prefix = image_character_bible.build_character_prefix(
        _scene_characters(plan, scene), art_directions.get_direction(plan["art_direction"])["consigne"])
    moment = (
        f"{scene['image_prompt'].strip()} Intention : {scene['visual_intention'].strip()} "
        f"Faire comprendre : {d['understand']}. Faire ressentir : {d['feel']}. Métaphore : {d['metaphor']}. "
        f"Indispensable : {d['essentials']}. À omettre : {d['omit']}. "
        f"Continuité : {d['continuity']}. {expression_for(scene)}"
    )
    base = image_prompt_builder.build_scene_prompt(
        [moment], None, prefix, "9:16", art_directions.style_bible(plan["art_direction"]), None)
    head = identity_block(plan, scene)
    return (head + "\n" if head else "") + FRAMING_RULES + "\n" + base


def reference_policy(plan: dict, scene_index: int, budget_headroom_usd: float, edit_cost_usd: float | None) -> str:
    """'text_bible' (défaut) ou 'reference_edit'. Le moteur a déjà constaté qu'une image de référence fige la pose
    (voir `image_character_bible`) : on ne l'emploie que si un personnage revient après ≥ 3 scènes d'absence, que le
    coût d'édition est CONNU et tient dans la marge. Sans tarif configuré : jamais."""
    scene = plan["scenes"][scene_index]
    present = set(scene.get("characters", []))
    if not present or edit_cost_usd is None or edit_cost_usd > budget_headroom_usd:
        return "text_bible"
    for cid in present:
        last_seen = max((i for i in range(scene_index) if cid in plan["scenes"][i].get("characters", [])), default=None)
        if last_seen is not None and scene_index - last_seen >= 3:
            return "reference_edit"
    return "text_bible"
