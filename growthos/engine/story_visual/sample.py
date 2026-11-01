"""Deux histoires d'exemple déterministes (un récit factuel sourcé, une fable fictive) + moteur de maquettes SANS COÛT.

`PlaceholderImageProvider` dessine des illustrations de substitution avec Pillow (aucun réseau, aucun fournisseur) et
déclare un coût fictif nul : il sert aux tests et à l'exemple de bout en bout. `build_sample(...)` rend un vrai MP4 vertical.
Les sources du récit factuel sont des références publiques CANONIQUES non rechargées pendant la fabrication : un humain
doit les vérifier avant tout usage public de ce récit (voir docs).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from . import art_directions, cost, orchestrator, overlay, render, schema, timing
from .orchestrator import ImageResult

FIXTURES = Path(__file__).parent / "fixtures"


def _scene(sid, beat, narration, intention, direction, prompt, text, tone, seconds, transition, camera, chars, kind="fact",
           sources=()):
    keys = ("understand", "feel", "metaphor", "essentials", "omit", "continuity")
    return {"id": sid, "beat": beat, "narration": narration, "visual_intention": intention,
            "visual_direction": dict(zip(keys, direction)), "image_prompt": prompt, "on_screen_text": text,
            "emotional_tone": tone, "duration_s": seconds, "transition": transition, "camera": camera,
            "characters": list(chars), "claim_kind": kind, "source_ids": list(sources)}


def factual_plan() -> dict:
    s = ("nobel", "wiki")
    return {
        "schema_version": 1, "story_id": "sample-penicillin", "story_type": "true", "language": "fr",
        "title": "La moisissure oubliée", "target_duration_s": 60, "factuality": "verified",
        "art_direction": "cinematic_story",
        "sources": [
            {"id": "nobel", "title": "The Nobel Prize in Physiology or Medicine 1945 — Alexander Fleming, Facts",
             "url": "https://www.nobelprize.org/prizes/medicine/1945/fleming/facts/"},
            {"id": "wiki", "title": "Penicillin — Wikipedia", "url": "https://en.wikipedia.org/wiki/Penicillin"},
        ],
        "characters": [{
            "id": "chercheur", "name": "Le chercheur",
            "appearance": "un chercheur d'âge mûr au visage fin et attentif, cheveux clairs coiffés en arrière",
            "proportions": "silhouette élancée, épaules étroites, grandes mains",
            "clothing": "blouse blanche usée, nœud papillon bordeaux", "palette": "blanc cassé, bordeaux, vert-de-gris",
            "distinctive": "un nœud papillon bordeaux toujours visible", "environment": "laboratoire encombré des années 1920",
            "negative": "lunettes, barbe, tenue moderne"}],
        "scenes": [
            _scene("s1", "hook", "Un tas de boîtes de culture oubliées, et une moisissure qui allait changer la médecine.",
                   "Une paillasse en désordre, une boîte au centre de la lumière.",
                   ("l'idée tient à un oubli", "curiosité", "la boîte oubliée comme un trésor", "une boîte de Petri, une paillasse",
                    "tout décor décoratif", "ouvre le récit, la boîte reviendra à la révélation"),
                   "Une boîte de Petri éclairée par un rayon de fenêtre sur une paillasse encombrée, laboratoire des années 1920.",
                   "Un oubli de vacances", "intrigue", 7, "cut", "push_in", [], "fact", s),
            _scene("s2", "setup", "En septembre 1928, Alexander Fleming rentre de vacances et retrouve son laboratoire de Londres.",
                   "Le chercheur franchit la porte de son laboratoire.",
                   ("le contexte : un laboratoire, un retour", "calme", "la porte comme seuil", "le chercheur, la porte",
                    "visage détaillé", "présente le personnage, même tenue ensuite"),
                   "Le chercheur de dos entre dans un laboratoire baigné d'une lumière de fin d'été.",
                   "Septembre 1928", "calme", 8, "crossfade", "push_in", ["chercheur"], "fact", s),
            _scene("s3", "conflict", "Sur l'une des boîtes, une moisissure s'est installée, ce qui arrive souvent. Il aurait pu la jeter.",
                   "Le chercheur se penche sur une boîte, la main hésitante au-dessus de l'évier.",
                   ("l'hésitation : jeter ou observer", "tension légère", "la main suspendue", "le chercheur, la boîte, l'évier",
                    "tout le reste", "fait écho à la boîte du premier plan"),
                   "Le chercheur penché sur une boîte de Petri, la main suspendue au-dessus d'un évier.",
                   "Il aurait pu la jeter.", "tension", 8, "crossfade", "push_in", ["chercheur"], "fact", s),
            _scene("s4", "development", "Mais autour de la moisissure, les bactéries avaient disparu. Il remarque la zone claire.",
                   "Gros plan de la boîte : un halo clair autour de la tache verte.",
                   ("voir la zone sans bactéries", "émerveillement", "le halo comme un cercle de protection", "la boîte, le halo",
                    "le visage", "gros plan de la boîte vue depuis la scène 3"),
                   "Gros plan sur une boîte de Petri : une tache verte entourée d'un halo clair, colonies à la périphérie.",
                   "Un halo sans bactéries", "émerveillement", 7, "crossfade", "push_in", [], "fact", s),
            _scene("s5", "development", "La moisissure, un Penicillium, produit quelque chose qui tue ces bactéries. Il l'appelle pénicilline.",
                   "Le chercheur, la boîte dans les mains, face à un tableau griffonné.",
                   ("nommer la substance", "excitation contenue", "un nom qui naît", "le chercheur, le tableau",
                    "formules illisibles", "même chercheur, même nœud papillon"),
                   "Le chercheur tient une boîte devant un tableau noir couvert de croquis griffonnés.",
                   "Penicillium → pénicilline", "excitation", 8, "crossfade", "pull_out", ["chercheur"], "fact", s),
            _scene("s6", "development", "Il faudra encore plus de dix ans, et d'autres chercheurs, pour en faire un médicament utilisable.",
                   "Un couloir de laboratoire qui s'étire, des silhouettes de chercheurs au loin.",
                   ("le chemin est long et collectif", "patience", "le couloir comme le temps", "un couloir, des silhouettes",
                    "le chercheur lui-même", "élargit le plan après les gros plans"),
                   "Plan large d'un long couloir de laboratoire aux portes ouvertes, silhouettes lointaines en blouse.",
                   "Plus de dix ans, et d'autres chercheurs", "patience", 8, "fade", "pull_out", [], "fact", s),
            _scene("s7", "revelation", "Découverte par hasard, oui. Mais il a fallu quelqu'un pour remarquer, et pour s'en étonner.",
                   "La boîte du début, désormais seule au centre d'une lumière chaude.",
                   ("le hasard n'a servi que parce qu'on a regardé", "émotion", "la boîte retrouvée", "la boîte, la lumière",
                    "tout le reste", "reprend le plan d'ouverture, cadrage plus serré"),
                   "La boîte de Petri seule, posée dans un rayon de lumière chaude, fond sombre.",
                   "Remarquer, c'est déjà découvrir", "émotion", 8, "fade", "push_in", [], "interpretation", s[:1]),
            _scene("s8", "resolution", "À retenir : une découverte commence souvent par un détail que l'on ne jette pas.",
                   "Le chercheur de profil, regardant la lumière.",
                   ("la leçon : s'arrêter sur l'anomalie", "apaisement", "la fenêtre comme ouverture", "le chercheur, la fenêtre",
                    "tout slogan", "clôt sur le personnage, même tenue"),
                   "Le chercheur de profil devant une fenêtre lumineuse, regard calme.",
                   "Ne pas jeter le détail", "apaisement", 7, "cut", "pull_out", ["chercheur"], "interpretation", s[:1]),
        ],
    }


def moral_plan() -> dict:
    return {
        "schema_version": 1, "story_id": "sample-fox-yes", "story_type": "moral", "language": "en",
        "title": "The Fox Who Always Said Yes", "target_duration_s": 60, "factuality": "fiction",
        "art_direction": "cinematic_story", "sources": [],
        "characters": [{
            "id": "rowan", "name": "Rowan",
            "appearance": "a slender young red fox with kind amber eyes and a white-tipped tail",
            "proportions": "long legs, slightly oversized ears, small narrow chest",
            "clothing": "a patched teal scarf", "palette": "rust red, teal, cream",
            "distinctive": "the patched teal scarf, always knotted on the left", "environment": "a misty autumn forest",
            "negative": "hat, backpack, human clothing"}],
        "scenes": [
            _scene("s1", "hook", "Rowan the fox had never once said no. Not to anyone. Not even to himself.",
                   "Rowan alone in a clearing, many shadows reaching for him.",
                   ("this fox has a problem with refusal", "unease", "many hands of shadow", "Rowan, long shadows",
                    "any text", "opens the fable, the scarf is introduced"),
                   "A slender red fox in a patched teal scarf stands in a misty clearing, many long shadows reaching toward him.",
                   "He never said no.", "unease", 7, "cut", "push_in", ["rowan"], "fiction"),
            _scene("s2", "setup", "The owl asked him to carry stones. The hares asked for his evenings. The crows asked for everything else.",
                   "Rowan carrying stones while hares and crows queue behind him.",
                   ("everyone asks, he gives", "heaviness", "the stack of stones", "Rowan, stones, hares, crows",
                    "background trees", "same scarf, same clearing as scene 1"),
                   "The red fox in the teal scarf carries a tall stack of stones, hares and crows waiting in a line behind him.",
                   "Yes. Yes. Yes.", "heaviness", 8, "crossfade", "pull_out", ["rowan"], "fiction"),
            _scene("s3", "conflict", "His own den grew cold and empty. No one noticed, because he never said so.",
                   "Rowan's tiny den, cold and dark, seen from outside in the rain.",
                   ("his own needs disappear", "loneliness", "a den with no light", "the den, the rain",
                    "other animals", "Rowan absent, his scarf hung inside"),
                   "A tiny fox den in tree roots, dark and cold in the rain, a teal scarf hanging inside the entrance.",
                   "No one noticed.", "loneliness", 8, "crossfade", "push_in", [], "fiction"),
            _scene("s4", "development", "One night, the weight was too much. A single stone slipped, and it rolled away down the hill.",
                   "Rowan's paws trembling, a stone rolling down a moonlit slope.",
                   ("the breaking point", "tension", "one stone leaving the stack", "Rowan, the rolling stone",
                    "crowd", "same night after the den"),
                   "The red fox in the teal scarf buckles under his stack of stones, one stone rolling down a moonlit slope.",
                   "One stone slipped.", "tension", 8, "crossfade", "push_in", ["rowan"], "fiction"),
            _scene("s5", "development", "Nothing terrible happened. The owl simply picked up the stone and said, 'Thank you for telling us.'",
                   "The owl gently lifts the stone, Rowan watching, surprised.",
                   ("refusing is survivable", "relief", "the owl's open wings", "owl, Rowan, stone",
                    "anger", "the owl appeared in scene 2"),
                   "A wise grey owl lifts a stone with a gentle smile, the red fox in the teal scarf watching, surprised.",
                   "Nothing terrible happened.", "relief", 8, "crossfade", "push_in", ["rowan"], "fiction"),
            _scene("s6", "development", "The next day, Rowan said his first small no. The hares waited. The world did not end.",
                   "Rowan standing upright before the hares, scarf blowing.",
                   ("practice, not perfection", "quiet courage", "an upright stance", "Rowan, hares",
                    "stones", "Rowan stands taller than in scene 1"),
                   "The red fox in the teal scarf stands upright before three hares at sunrise, scarf lifted by the wind.",
                   "A small no.", "courage", 8, "fade", "pull_out", ["rowan"], "fiction"),
            _scene("s7", "revelation", "And Rowan understood: every yes to others had been a no to himself.",
                   "Rowan at the den entrance, a warm light inside.",
                   ("yes and no are linked", "insight", "the lit den", "Rowan, den, light",
                    "the crowd", "the den from scene 3, now lit"),
                   "The red fox in the teal scarf at the entrance of his den, warm light glowing inside.",
                   "Every yes is a no.", "insight", 8, "fade", "push_in", ["rowan"], "fiction"),
            _scene("s8", "resolution", "A kind yes needs a free no. That is how Rowan finally came home.",
                   "Rowan asleep in his warm den, the scarf folded.",
                   ("balance is kindness", "peace", "sleep", "Rowan sleeping",
                    "moral slogans", "closes inside the den"),
                   "The red fox asleep in his warm den, the teal scarf folded beside him, soft light.",
                   "A kind yes needs a free no.", "peace", 7, "cut", "pull_out", ["rowan"], "fiction"),
        ],
    }


def write_fixtures() -> list[Path]:
    paths = []
    for name, plan in (("factual_penicillin_fr", factual_plan()), ("moral_fox_en", moral_plan())):
        path = FIXTURES / f"{name}.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


class PlaceholderImageProvider:
    """Illustrations de substitution, déterministes, SANS réseau ni coût. Compte ses appels (pour les tests)."""

    def __init__(self):
        self.calls: list[str] = []
        self.fail_next = 0  # nombre d'appels suivants à faire échouer (test de reprise)

    def __call__(self, prompt: str, out_path: str, *, model: str, quality: str, reference_path: str | None = None) -> ImageResult:
        self.calls.append(prompt)
        if self.fail_next > 0:
            self.fail_next -= 1
            return ImageResult(None, 0.0, None, "provider_error")
        seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        palette = [(27, 58, 75), (224, 164, 88), (200, 90, 60), (244, 235, 221), (60, 100, 90)]
        bg, accent = palette[seed % 5], palette[(seed >> 3) % 5]
        image = Image.new("RGB", (1024, 1536), bg)
        draw = ImageDraw.Draw(image)
        for y in range(1536):  # dégradé vertical doux
            shade = round(40 * y / 1536)
            draw.line([(0, y), (1024, y)], fill=tuple(max(0, c - shade) for c in bg))
        cx, cy = 300 + seed % 420, 420 + (seed >> 5) % 360
        draw.ellipse([cx - 230, cy - 230, cx + 230, cy + 230], fill=accent)
        draw.polygon([(cx - 140, 1536), (cx, cy + 120), (cx + 140, 1536)], fill=tuple(max(0, c - 60) for c in accent))
        image.save(out_path, "JPEG", quality=90)
        return ImageResult(out_path, 0.0, {"input_text": 0, "input_image": 0, "output": 0})


def _tone(path: Path, seconds: float) -> None:
    """Narration de substitution : un souffle sinusoïdal bas, de la durée estimée (aucune synthèse vocale)."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=180:sample_rate=48000:duration={seconds:.3f}",
                    "-af", "volume=0.05", "-c:a", "aac", str(path)], check=True, capture_output=True)


def build_sample(plan: dict, out_dir: str | Path, tenant_id: str = "sample", *, fps: int = render.FPS, preset: str = "veryfast") -> dict:
    """Plan -> MP4 vertical complet, sans aucun appel payant. Retourne un rapport (timeline, lisibilité, coût réel = 0)."""
    errors = schema.validate_story_plan(plan)
    if errors:
        raise ValueError("invalid plan: " + "; ".join(errors))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    provider = PlaceholderImageProvider()
    tracker = cost.BudgetTracker(cost.Budget())
    manifest = orchestrator.generate_scene_images(plan, tenant_id=tenant_id, work_dir=out / "work", provider=provider,
                                                  tracker=tracker, expected_unit_usd=0.0)
    cards, readability, audio, layers = [], [], [], []
    for scene in plan["scenes"]:
        card = out / "work" / f"card-{scene['id']}.jpg"
        layer = out / "work" / f"text-{scene['id']}.png"
        report = overlay.compose_layers(manifest[scene["id"]]["path"], scene["on_screen_text"], plan["art_direction"], card, layer)
        readability.append(report)
        cards.append(card)
        layers.append(layer if report["has_layer"] else None)
        tone = out / "work" / f"voice-{scene['id']}.m4a"
        _tone(tone, timing.estimate_audio_seconds(scene["narration"], plan["language"]))
        audio.append(tone)
    measured = {s["id"]: render.audio_duration(a) for s, a in zip(plan["scenes"], audio)}
    timeline = timing.schedule(plan, measured)
    overlaps = timing.check_no_overlap(timeline)
    if overlaps:
        raise ValueError("; ".join(overlaps))
    video = out / f"{plan['story_id']}.mp4"
    info = render.render_story(cards, timeline, audio, video, out / "work", fps=fps, preset=preset, text_layers=layers)
    (out / f"{plan['story_id']}.srt").write_text(timing.srt(plan, timeline), encoding="utf-8")
    return {"video": str(video), "probe": info, "timeline": timeline, "readability": readability,
            "actual_cost_usd": tracker.total, "placeholder": True}
