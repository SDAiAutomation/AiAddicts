#!/usr/bin/env python3
"""Rendu LOCAL d'un récit illustré Story Studio avec les VRAIS fournisseurs (images OpenAI, voix ElevenLabs), coût plafonné.

But : juger la qualité d'une vraie vidéo AVANT de câbler base de données, worker et site de test. Aucune base, aucun crédit,
aucune publication : le plan vient d'une fixture, les fichiers sont écrits hors dépôt (défaut ~/story_visual_local_run).

À lancer sur la machine qui possède le `.env` (jamais envoyé nulle part, jamais affiché). Garanties :
  - DRY-RUN par défaut : estime le coût et s'arrête. Les appels payants exigent `--go`.
  - `--voice-rate` est OBLIGATOIRE (votre tarif ElevenLabs confirmé, en $ pour 1 000 caractères) : aucune valeur par défaut.
  - Refus si l'estimation est incomplète (un poste sans tarif) ou dépasse le plafond (`--cap`, défaut 1 $, maximum 1 $).
  - Le moteur impose lui-même le plafond de dépense (`BudgetTracker.reserve` avant chaque appel payant, échec fermé).
  - Image : modèle `gpt-image-2.5-flare`, qualité `low` (les seules dont le coût a été mesuré). Script : déjà écrit (fixture), 0 $.
  - Les clés sont signalées « présente / absente », jamais affichées.

Exemple : python growthos/scripts/story_visual_local_run.py --voice-rate 0.18                                   # dry-run
          python growthos/scripts/story_visual_local_run.py --voice-rate 0.18 --env-file C:\\chemin\\.env --go   # appels payants
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from growthos.engine.story_visual import cost, orchestrator, pipeline, schema, voice  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "engine" / "story_visual" / "fixtures"
MAX_CAP_USD = 1.0
CORENTIN = "IHngRooVccHyPqB4uQkG"
MEASURED_IMAGE_USD = 0.0092
TENANT = "local"


def load_env_file(path: Path) -> None:
    """Charge le fichier dans CE processus uniquement (python-dotenv, sans surcharge de l'environnement existant)."""
    from dotenv import load_dotenv
    if not path.is_file():
        raise SystemExit(f"STOP : fichier d'environnement introuvable : {path}")
    load_dotenv(path, override=False)


def build_env(args) -> dict:
    """Environnement du run : tarifs explicites, modèle et qualité mesurés. Posé aussi dans os.environ (le routeur d'images le lit)."""
    forced = {
        "STORY_IMAGE_USD_EACH": str(args.image_usd), "ELEVENLABS_USD_PER_1K_CHARS": str(args.voice_rate),
        "SCRIPT_PRICE_IN_PER_M": "0", "SCRIPT_PRICE_OUT_PER_M": "0", "STORY_PLAN_TOKENS_IN": "0", "STORY_PLAN_TOKENS_OUT": "0",
        "STORY_RENDER_USD": "0", "STORY_STORAGE_USD": "0",
        "IMAGE_MODEL_PREMIUM": "gpt-image-2.5-flare", "IMAGE_FINAL_QUALITY": "low",
    }
    os.environ.update(forced)
    return dict(os.environ)


def load_plan(name: str, voice_id: str) -> dict:
    path = FIXTURES / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"STOP : fixture introuvable : {name} (disponibles : "
                         + ", ".join(p.stem for p in sorted(FIXTURES.glob('*.json')) if 'parity' not in p.stem) + ")")
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["voice_id"] = voice_id
    errors = schema.validate_story_plan(plan)
    if errors:
        raise SystemExit("STOP : plan invalide : " + "; ".join(errors[:3]))
    return plan


def run(args) -> int:
    if args.env_file:
        load_env_file(Path(args.env_file).expanduser())
    openai_key, eleven_key = bool(os.environ.get("OPENAI_API_KEY")), bool(os.environ.get("ELEVENLABS_API_KEY"))
    print(f"OPENAI_API_KEY : {'présente' if openai_key else 'ABSENTE'}  |  ELEVENLABS_API_KEY : {'présente' if eleven_key else 'ABSENTE'}  |  "
          f"ffmpeg : {'présent' if shutil.which('ffmpeg') and shutil.which('ffprobe') else 'ABSENT'}")
    env = build_env(args)
    plan = load_plan(args.fixture, args.voice_id)
    estimate = cost.estimate_episode(plan, env)
    budget = cost.Budget(args.cap, min(args.cap, 0.5))
    decision = cost.check_budget(estimate, budget)
    print(f"Récit : {plan['title']} | {estimate['scenes']} scènes | {estimate['voice_characters']} caractères de narration | voix {args.voice_id}")
    for line in estimate["lines"]:
        if line["quantity"]:
            print(f"  {line['item']:<16} {line['usd'] if line['usd'] is not None else 'NON CHIFFRÉ'} $  ({line['source']})")
    print(f"Estimation : {estimate['total_usd']:.4f} $ (statut : {decision['status']}) pour un plafond de {args.cap:.2f} $")
    print("  Une image qui échoue peut être retentée (3 essais max par scène) : le plafond du moteur borne la dépense réelle.")
    if not decision["allowed"] or estimate["unpriced"]:
        print("STOP : " + decision["message"])
        return 2
    if not args.go:
        print("DRY-RUN terminé : rien n'a été appelé. Relancez avec --go (clés requises) pour le rendu payant.")
        return 0
    if not (openai_key and eleven_key and shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("STOP : il manque une clé (OPENAI_API_KEY, ELEVENLABS_API_KEY) ou ffmpeg/ffprobe. Aucun appel.")
        return 2

    work = Path(args.out).expanduser() / time.strftime("%Y%m%d-%H%M%S")
    work.mkdir(parents=True, exist_ok=True)
    ports = pipeline.Ports(image_provider=orchestrator.openai_provider(), voice_provider=voice.elevenlabs_provider(env),
                           env=env, budget=budget, progress=lambda label: print(f"  ... {label}"),
                           render_fps=args.fps, render_preset=args.preset)
    print(f"RENDU RÉEL en cours (appels payants). Dossier : {work}")
    try:
        result = pipeline.run({"story_plan": plan}, ports, work, tenant_id=TENANT)
    except (pipeline.PipelineError, cost.BudgetExceeded) as exc:
        print(f"ÉCHEC : {exc}")
        print("  Des appels payants ont pu avoir lieu avant l'échec : voir les fichiers du dossier ci-dessus.")
        return 1
    report = result["cost"]
    print(f"VIDÉO : {result['video']}")
    print(f"Dépense : {report['spent_usd']:.4f} $ {report['spent_by_kind']} | chiffrage complet : {report['complete']}")
    print(f"À revoir : {result['needs_review']} {result['review']}" if result["review"] else "Contrôle qualité : aucun problème détecté.")
    print("Jugement artistique : à vous. Ouvrez le MP4 ; sous-titres .srt à côté.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--voice-rate", type=float, required=True, help="votre tarif ElevenLabs confirmé, $ pour 1 000 caractères (obligatoire)")
    parser.add_argument("--image-usd", type=float, default=MEASURED_IMAGE_USD, help="coût d'une image (défaut : 0,0092 $ mesuré)")
    parser.add_argument("--cap", type=float, default=MAX_CAP_USD, help="plafond de dépense en $ (défaut et maximum : 1)")
    parser.add_argument("--fixture", default="factual_penicillin_fr", help="plan de départ (fichier de engine/story_visual/fixtures)")
    parser.add_argument("--voice-id", default=CORENTIN)
    parser.add_argument("--env-file", help="fichier .env à charger dans ce processus")
    parser.add_argument("--out", default=str(Path.home() / "story_visual_local_run"), help="dossier de sortie, hors dépôt")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--preset", default="veryfast", choices=["ultrafast", "veryfast", "fast", "medium"])
    parser.add_argument("--go", action="store_true", help="autorise les appels payants")
    args = parser.parse_args(argv)
    if not 0 < args.cap <= MAX_CAP_USD or args.voice_rate <= 0 or args.image_usd < MEASURED_IMAGE_USD:
        raise SystemExit(f"STOP : --cap doit être dans ]0 ; {MAX_CAP_USD}], --voice-rate > 0 et --image-usd >= {MEASURED_IMAGE_USD} (coût mesuré).")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
