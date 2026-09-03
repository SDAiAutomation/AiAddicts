"""GrowthOS MVP CLI — script.json -> voix off -> vidéo texte-carte -> package de publication.

Usage:
    python main.py content/scripts/exemple-01.json
    python main.py content/scripts/exemple-01.json --voice 21m00Tcm4TlvDq8ikWAM
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine.assembler import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script_path", help="chemin vers le script .json")
    parser.add_argument(
        "--voice",
        dest="voice",
        help="voice_id ElevenLabs à utiliser (prioritaire sur le script et config/voices.json)",
    )
    args = parser.parse_args()
    run(args.script_path, voice_override=args.voice)
