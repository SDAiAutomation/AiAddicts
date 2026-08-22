#!/usr/bin/env python3
"""Point d'entrée CLI du moteur de génération Faceless Kids Stories.

Usage :
    python main.py stories/histoire-01.json
"""
from __future__ import annotations

import argparse
import sys

from engine.assembler import AssemblyError
from engine.pipeline import generate_story
from engine.tts import TTSError
from engine.video import VideoGenerationError


def _print_progress(step: str, detail: str) -> None:
    print(f"[{step}] {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère une histoire vidéo complète (voix off + vidéo + montage) depuis un script JSON."
    )
    parser.add_argument("story_path", help="Chemin du fichier stories/*.json")
    args = parser.parse_args()

    try:
        final_path = generate_story(args.story_path, on_progress=_print_progress)
    except (TTSError, VideoGenerationError, AssemblyError, FileNotFoundError, ValueError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Vidéo finale : {final_path}")


if __name__ == "__main__":
    main()
