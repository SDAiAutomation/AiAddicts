"""Explainer à partir d'un sujet STRUCTURÉ, sans aucun modèle de langage : générateur déterministe -> (voix ElevenLabs) -> rendu.

    python -m engine.explainer.structured compound_interest out_dir --capital 100 --rate 10 --years 10 [--lang fr|en]
                                          [--currency eur|usd] [--no-voice] [--no-render]

Seule la voix passe par un service externe (ElevenLabs, clé lue dans l'environnement / `.env`) ; `--no-voice` rend une vidéo muette,
gratuite, aux temps estimés. Coût du modèle : 0 $.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import generators, pipeline, timeline, voiceover


def run(generator: str, params: dict, out_dir: str | Path, lang: str = "fr", voice: bool = True, do_render: bool = True, log=print) -> dict:
    spec = generators.build(generator, params, lang)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    voice_report = None
    if voice:
        narration, words = timeline.estimate_narration(spec["lines"])
        log("Voix ElevenLabs…")
        voice_report = voiceover.build_voiceover(narration, timeline.total_duration(narration, words), out / "voice")
        log(f"  {voice_report['charsBilledThisRun']} caractères facturés")
    return pipeline.generate(spec["topic"], out, spec=spec, voice_report=voice_report, voice_wav=voice_report["wav"] if voice_report else None,
                             do_render=do_render, use_critic=False, log=log)


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    if len(argv) < 2 or argv[0] not in generators.REGISTRY:
        print(__doc__)
        return 2
    opts = {k[2:]: argv[i + 1] for i, k in enumerate(argv) if k.startswith("--") and k not in ("--no-voice", "--no-render") and i + 1 < len(argv)}
    lang = opts.pop("lang", "fr")
    params = {k: v for k, v in opts.items()}
    report = run(argv[0], params, argv[1], lang=lang, voice="--no-voice" not in argv, do_render="--no-render" not in argv)
    print(json.dumps({"video": report.get("video"), "fallbacks": report.get("fallbacks"), "usd": report["spend"]["totalUsd"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
