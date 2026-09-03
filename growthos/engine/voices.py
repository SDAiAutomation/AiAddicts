"""Resolve which ElevenLabs voice a script should be narrated with.

Resolution order (first hit wins):

1. an explicit override (the `--voice` CLI flag)
2. the script's own `voice_id`
3. `config/voices.json`, keyed by the script's `niche`
4. `config/voices.json` "default" key

The interactive-picker model (facelessreels.com style) is deliberately not
used: the pipeline is a non-interactive CLI meant to stay scriptable. A
niche -> voice_id table gives the same "pick per topic" behaviour without a
prompt, and matches the schema's account/strategy model where the voice is
really an account-level property.
"""
import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "voices.json"
_PLACEHOLDER_MARKERS = ("REMPLACER", "REPLACE", "<", "your_", "xxx")


def load_voice_map(path: Path | None = None) -> dict:
    """Read config/voices.json. Missing or malformed file -> empty map."""
    path = path or _CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, str) and not k.startswith("_")}


def _usable(voice_id: str | None) -> bool:
    if not voice_id or not voice_id.strip():
        return False
    return not any(m in voice_id for m in _PLACEHOLDER_MARKERS)


def resolve_voice(script: dict, override: str | None = None, voice_map: dict | None = None) -> str:
    """Return the voice_id to narrate `script` with, or raise ValueError."""
    voice_map = load_voice_map() if voice_map is None else voice_map
    niche = script.get("niche")

    candidates = [
        ("--voice", override),
        ("le champ 'voice_id' du script", script.get("voice_id")),
        (f"config/voices.json (niche '{niche}')", voice_map.get(niche) if niche else None),
        ("config/voices.json (clé 'default')", voice_map.get("default")),
    ]
    for _source, value in candidates:
        if _usable(value):
            return value.strip()

    raise ValueError(
        "aucune voix ElevenLabs utilisable — renseigne l'une de ces sources :\n"
        "  - l'option --voice <id>\n"
        "  - le champ 'voice_id' du script\n"
        f"  - une entrée pour la niche '{niche}' dans config/voices.json\n"
        "  - une clé 'default' dans config/voices.json"
    )
