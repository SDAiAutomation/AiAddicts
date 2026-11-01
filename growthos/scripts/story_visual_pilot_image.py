#!/usr/bin/env python3
"""Pilote artistique Story Studio 2.0 : UNE illustration via l'intégration OpenAI Images existante, coût borné.

À lancer sur la machine qui possède le `.env` (jamais envoyé nulle part, jamais affiché). Garanties :
  - DRY-RUN par défaut : calcule la borne de coût et s'arrête. L'appel payant exige `--go`.
  - UNE seule requête HTTP, AUCUN retry, AUCUNE régénération (timeout = coût inconnu, signalé, jamais retenté).
  - Refus si la borne de coût n'est pas CALCULABLE ou dépasse le plafond (défaut 0,50 $). Les tarifs ne sont pas codés en dur :
    lisez-les sur la page officielle des tarifs OpenAI du modèle utilisé et donnez-les en variables d'environnement.
  - Aucune valeur de secret n'est lue pour affichage : la clé est signalée « présente / absente ».
  - L'image est un artefact de test écrit hors dépôt ; rien n'est publié.

Variables requises pour que la borne soit calculable (tous en $ par MILLION de jetons, ou nombre de jetons) :
  OPENAI_IMAGE_MODEL                      modèle réellement utilisé (pas de défaut : on ne devine pas un modèle payant)
  IMAGE_PRICE_IMAGE_OUT_PER_M             tarif officiel, jetons image en SORTIE
  IMAGE_PRICE_TEXT_IN_PER_M               tarif officiel, jetons texte en ENTRÉE
  STORY_IMAGE_MAX_OUTPUT_TOKENS           nombre MAXIMAL de jetons de sortie d'une image à cette taille/qualité (table officielle)
Qualité : `--quality low|medium|high` (défaut low, la plus bornée). Taille : 1024x1536 (portrait, comme le moteur).

Exemple : python growthos/scripts/story_visual_pilot_image.py --env-file ~/Faceloop/AiAddicts/.env            # dry-run
          python growthos/scripts/story_visual_pilot_image.py --env-file ~/Faceloop/AiAddicts/.env --go       # appel payant
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests  # noqa: E402

from growthos.engine import openai_images  # noqa: E402
from growthos.engine.story_visual import visual_direction  # noqa: E402

CAP_USD = 0.50
SIZE = "1024x1536"
TOPIC = "Pourquoi les personnes gentilles ont-elles du mal à dire non ?"

PILOT_PLAN = {
    "art_direction": "cinematic_story",
    "characters": [{
        "id": "gentle", "name": "La personne gentille",
        "appearance": "une femme d'une trentaine d'années au visage doux et fatigué, un sourire poli qui ne monte pas jusqu'aux yeux",
        "proportions": "silhouette fine, épaules légèrement voûtées", "clothing": "un long cardigan moutarde, un foulard bleu nuit",
        "palette": "moutarde, bleu nuit, crème", "distinctive": "le foulard bleu nuit, toujours noué à gauche",
        "negative": "changer de tenue, de coiffure ou de palette"}],
    "scenes": [{
        "id": "s1", "characters": ["gentle"],
        "image_prompt": (
            "Métaphore visuelle immédiate : une femme douce tient grande ouverte une lourde porte pour une longue file de silhouettes "
            "qui attendent de passer, ses bras tendus tremblent sous l'effort ; derrière elle, sa propre maison est plongée dans le noir, "
            "fenêtre éteinte. Lumière chaude et dorée sur la foule, lumière froide et bleutée sur elle. Composition verticale, la femme "
            "décentrée sur le tiers gauche, la porte et la file qui s'étirent vers l'horizon, bas du cadre calme et sombre."),
        "visual_intention": "Montrer qu'ouvrir la porte à tous, c'est laisser sa propre maison dans le noir.",
        "emotional_tone": "épuisement doux, gentillesse qui s'oublie",
        "visual_direction": {
            "understand": "être gentil sans limite se paie de soi-même", "feel": "tendresse inquiète et un peu de tristesse",
            "metaphor": "tenir la porte à tout le monde pendant que sa maison s'éteint",
            "essentials": "la femme, la porte, la file de silhouettes, la maison sombre", "omit": "tout texte, tout décor secondaire",
            "continuity": "première image de l'histoire"}}],
}


def load_env_file(path: Path) -> None:
    """Charge le fichier dans CE processus uniquement (python-dotenv, sans surcharge de l'environnement existant)."""
    from dotenv import load_dotenv
    if not path.is_file():
        raise SystemExit(f"STOP : fichier d'environnement introuvable : {path}")
    load_dotenv(path, override=False)


def _num(name: str) -> float | None:
    try:
        value = float(os.environ.get(name, "").strip())
    except ValueError:
        return None
    return value if math.isfinite(value) and value >= 0 else None


def cost_bound(prompt: str, env_num=_num) -> dict:
    """Borne SUPÉRIEURE du coût, ou `computable: False` avec les variables manquantes. Entrée texte majorée à 1 jeton par caractère."""
    needed = {"IMAGE_PRICE_IMAGE_OUT_PER_M": env_num("IMAGE_PRICE_IMAGE_OUT_PER_M"),
              "IMAGE_PRICE_TEXT_IN_PER_M": env_num("IMAGE_PRICE_TEXT_IN_PER_M"),
              "STORY_IMAGE_MAX_OUTPUT_TOKENS": env_num("STORY_IMAGE_MAX_OUTPUT_TOKENS")}
    missing = [k for k, v in needed.items() if v is None]
    if missing:
        return {"computable": False, "missing": missing}
    text_tokens = len(prompt)
    bound = (needed["STORY_IMAGE_MAX_OUTPUT_TOKENS"] * needed["IMAGE_PRICE_IMAGE_OUT_PER_M"]
             + text_tokens * needed["IMAGE_PRICE_TEXT_IN_PER_M"]) / 1_000_000
    return {"computable": True, "bound_usd": round(bound, 6), "text_tokens_upper": text_tokens,
            "max_output_tokens": needed["STORY_IMAGE_MAX_OUTPUT_TOKENS"], "basis": "ESTIMATION (borne), jamais une mesure"}


def build_prompt() -> str:
    return visual_direction.build_image_prompt(PILOT_PLAN, 0)


def run(args, post=requests.post) -> int:
    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())
    print(f"OPENAI_API_KEY : {'présente' if os.environ.get('OPENAI_API_KEY') else 'ABSENTE'}")
    model = os.environ.get("OPENAI_IMAGE_MODEL", "").strip()
    print(f"Modèle (OPENAI_IMAGE_MODEL) : {model or 'NON DÉFINI'}  | qualité : {args.quality}  | taille : {SIZE}")
    prompt = build_prompt()
    bound = cost_bound(prompt)
    print(f"Prompt : {len(prompt)} caractères (voir le rapport JSON pour le texte complet)")
    if not os.environ.get("OPENAI_API_KEY"):
        print("STOP : clé absente de l'environnement chargé.")
        return 2
    if not model:
        print("STOP : OPENAI_IMAGE_MODEL doit être défini explicitement (aucun modèle par défaut pour un appel payant).")
        return 2
    if not bound["computable"]:
        print("STOP : borne de coût non calculable. Variables manquantes : " + ", ".join(bound["missing"]))
        return 2
    print(f"Borne de coût (ESTIMATION) : {bound['bound_usd']:.4f} $ pour un plafond de {args.cap:.2f} $")
    if bound["bound_usd"] > args.cap:
        print("STOP : la borne dépasse le plafond. Aucun appel.")
        return 2
    if not args.go:
        print("DRY-RUN terminé : rien n'a été appelé. Relancez avec --go pour l'unique appel payant.")
        return 0

    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = out_dir / f"pilot-{stamp}.jpg"
    report_path = out_dir / f"pilot-{stamp}.json"
    payload = {"model": model, "prompt": prompt, "size": SIZE, "quality": args.quality, "n": 1, "output_format": "jpeg"}
    report = {"topic": TOPIC, "model": model, "quality": args.quality, "size": SIZE, "prompt": prompt, "cap_usd": args.cap,
              "cost_bound": bound, "calls": 1, "retries": 0, "image": str(image_path)}
    try:  # UNE requête, aucun retry
        resp = post(openai_images.GENERATIONS_URL, headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    json=payload, timeout=180)
    except requests.RequestException as exc:
        report.update(status="network_error", error=type(exc).__name__,
                      cost={"kind": "UNKNOWN", "note": "la requête a pu être facturée : vérifier le tableau de bord OpenAI"})
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ÉCHEC réseau : aucune nouvelle tentative (coût possible inconnu). Rapport :", report_path)
        return 1
    if resp.status_code != 200:
        report.update(status=f"http_{resp.status_code}", error=resp.text[:300],
                      cost={"kind": "UNKNOWN", "note": "erreur API ; en principe non facturée, à vérifier"})
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"ÉCHEC HTTP {resp.status_code} : aucune nouvelle tentative. Rapport :", report_path)
        return 1
    openai_images._decode_and_write(resp, str(image_path))
    usage = openai_images.pop_last_usage()
    out_price, in_price = _num("IMAGE_PRICE_IMAGE_OUT_PER_M"), _num("IMAGE_PRICE_TEXT_IN_PER_M")
    image_in = _num("IMAGE_PRICE_IMAGE_IN_PER_M") or 0.0
    if usage and out_price is not None and in_price is not None:
        measured = (usage["output"] * out_price + usage["input_text"] * in_price + usage["input_image"] * image_in) / 1_000_000
        cost = {"kind": "MEASURED", "usd": round(measured, 6), "usage": usage,
                "basis": "usage renvoyé par l'API x tarifs que vous avez configurés",
                "within_bound": usage["output"] <= bound["max_output_tokens"]}
    else:
        cost = {"kind": "UNKNOWN", "usage": usage, "note": "usage absent : coût non mesuré, seule la borne (estimation) existe"}
    report.update(status="ok", cost=cost)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Image : {image_path}\nRapport : {report_path}\nCoût : {cost['kind']}" + (f" {cost['usd']:.4f} $" if cost["kind"] == "MEASURED" else ""))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--env-file", help="fichier .env à charger dans ce processus (jamais affiché)")
    parser.add_argument("--quality", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--cap", type=float, default=CAP_USD)
    parser.add_argument("--out-dir", default="~/faceloop_pilot")
    parser.add_argument("--go", action="store_true", help="autorise l'UNIQUE appel payant")
    args = parser.parse_args(argv)
    if not math.isfinite(args.cap) or not 0 < args.cap <= CAP_USD:
        raise SystemExit(f"STOP : le plafond doit être dans ]0 ; {CAP_USD}] $")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
