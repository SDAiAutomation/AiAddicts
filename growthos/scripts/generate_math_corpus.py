"""Génère des vidéos de maths de bout en bout SANS écrire dans Supabase.

Appelle le même `engine.assembler._generate` que le worker (voix ElevenLabs, alignement mot à mot,
plan d'étapes, rendu Manim, assemblage ffmpeg), mais ne crée ni organisation, ni compte, ni
`content_item`. Sert à comparer des rendus et à rejouer le corpus de qualité.

    python scripts/generate_math_corpus.py content/scripts/maths-quality/ref-3x6.json --out output/math-quality/run1
    python scripts/generate_math_corpus.py content/scripts/maths-quality/c*.json --out output/math-quality/run1

Variables utiles : MATH_RENDERER=manim (qualité finale, défaut ici ; échec = erreur explicite),
auto (repli Pillow tracé), pillow (aperçu). Appels payants : ElevenLabs uniquement (une synthèse par
bloc, réutilisée si le dossier de sortie existe déjà).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
os.environ.setdefault("MATH_RENDERER", "manim")

from engine import script as script_module  # noqa: E402
from engine.assembler import _generate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scripts", nargs="+", help="un ou plusieurs script.json")
    parser.add_argument("--out", required=True, help="dossier de sortie (une sous-arborescence par vidéo)")
    parser.add_argument("--voice", help="voice_id ElevenLabs (sinon la voix du script / de la niche)")
    args = parser.parse_args()

    failures = 0
    for path in args.scripts:
        started = time.time()
        try:
            data = script_module.load_script(path)  # refuse ici une résolution fausse : AUCUN appel payant
        except ValueError as exc:
            print(f"REFUSÉ  {path} : {exc}")
            failures += 1
            continue
        try:
            final, work_dir, _metrics = _generate(data, args.out, args.voice)
        except Exception as exc:  # noqa: BLE001 — on continue le corpus, l'erreur reste visible
            print(f"ÉCHEC   {path} : {type(exc).__name__}: {exc}")
            failures += 1
            continue
        reports = sorted(Path(work_dir, "images").glob("*.render.json"))
        engines = [json.loads(p.read_text(encoding="utf-8")).get("engine") for p in reports]
        print(f"OK      {path} -> {final} ({time.time() - started:.0f}s, moteur(s) de rendu : {engines or 'aucun'})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
