"""GrowthOS MVP CLI — script.json -> voix off -> vidéo texte-carte -> package de publication.

Usage:
    python main.py content/scripts/exemple-01.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from engine.assembler import run

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python main.py <chemin_vers_script.json>")
        sys.exit(1)
    run(sys.argv[1])
