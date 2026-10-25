"""Standard Video script -> Story Studio scene contract (animation schema 2). Pure: no IO, no model call, no provider.

Story Studio does not get a narrative engine of its own. A story is written the way every Standard Video script is (hook, points,
call to action; same generator, same retention diagnostics, same cost caps), and this module only TRANSLATES it into scenes the
rig can play. It validates the Standard script with the Standard validator, runs the Standard retention diagnostics on it, splits
blocks that are too long for one scene, and fills the staging (speaker, framing, setting, listeners) with plain rules. Anything the
author wants to control (who speaks, acting, setting, nature of a statement) comes in as optional hints on the block.

Block hints read here (all optional, all ignored by Standard): `speaker` (a character id; default the narrator), `setting`,
`acting` ({character_id: [mood, gesture]}), `nature` ("fact" | "interpretation" | "hypothesis" | "fiction"), `source_ids`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import retention, script as standard_script
from . import contract, pipeline

# where each pack's character stands and faces, as in the cast of the editor (web cast.ts)
LAYOUT = {"pip_v1": ("right", "left"), "rosette_v1": ("left", "right")}
SETTING_CYCLE = ("street", "clock_shop", "cafe_terrace", "factory_alley")
# a new setting begins at the blocks that change the place of the story
SETTING_CHANGES = {"establish", "reveal", "payoff"}
SHOT_TYPES = {"wide": "wide", "medium": "medium", "close_up": "close_up", "insert": "insert", "pov": "medium"}
_SENTENCE = re.compile(r"[^.!?…]+(?:[.!?…]+|$)")


@dataclass
class AdaptResult:
    script: dict                                   # {"content_format": "story", "title": ..., "story": {...}}
    errors: list = field(default_factory=list)     # contract errors (empty = the pipeline will accept it)
    retention_issues: list = field(default_factory=list)   # Standard retention diagnostics worth a human look (never blocking)


def split_text(text: str, limit: int = contract.MAX_SHOT_DIALOGUE_CHARS) -> list:
    """Cuts a block at sentence ends so that every piece fits one scene; a single sentence longer than the limit is cut at a word."""
    pieces, current = [], ""
    for sentence in (s.strip() for s in _SENTENCE.findall(text.strip())):
        if not sentence:
            continue
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def adapt(script: dict, *, narrator: dict, characters: list, duration_target_s: int, editorial: dict | None = None,
          style_id: str | None = None, music_id: str | None = None, catalog: dict | None = None) -> AdaptResult:
    """`script`: a Standard script (title, niche, account, blocks...). `narrator`: {"id", "name", "voice_id"}.
    `characters`: [{"id", "name", "voice_id", "pack_id"}] (they listen on screen and speak when a block names them).
    Raises ValueError when the Standard script itself is invalid (the Standard validator's message)."""
    standard_script.validate_script(script)
    blocks = script["blocks"]
    ids = {c["id"] for c in characters}
    shots, listeners = [], []
    for c in characters[: contract.MAX_ACTORS_PER_SHOT]:
        side, facing = LAYOUT.get(c["pack_id"], ("center", "right"))
        listeners.append((c["id"], side, facing))

    setting_index = 0
    for i, block in enumerate(blocks):
        if i > 0 and block.get("visualPurpose") in SETTING_CHANGES:
            setting_index += 1
        setting = block.get("setting") or SETTING_CYCLE[setting_index % len(SETTING_CYCLE)]
        speaker = block.get("speaker") if block.get("speaker") in ids else narrator["id"]
        narrated = speaker == narrator["id"]
        shot_type = SHOT_TYPES.get(block.get("shotType"), "wide" if i % 2 == 0 else "medium")
        if narrated and shot_type == "close_up":
            shot_type = "medium"  # a narrator has no face to frame
        acting = block.get("acting") if isinstance(block.get("acting"), dict) else {}
        actors = []
        for cid, side, facing in listeners:
            mood, gesture = (acting.get(cid) or ["neutral", "idle"])[:2]
            actors.append({"character_id": cid, "side": side, "facing": facing, "mood": mood, "gesture_id": gesture})
        for piece in split_text(str(block.get("text", ""))):
            shot = {
                "id": f"s{len(shots) + 1}", "setting_id": setting, "shot_type": shot_type, "speaker_id": speaker,
                "dialogue": piece, "actors": [dict(a) for a in actors], "transition_in": "cut",
            }
            if block.get("nature") is not None:
                shot["nature"] = block["nature"]
            if block.get("source_ids"):
                shot["source_ids"] = list(block["source_ids"])
            if block.get("role"):
                shot["intent"] = f"{block['role']}" + (f" · {block['visualPurpose']}" if block.get("visualPurpose") else "")
            shots.append(shot)

    story = {
        "version": contract.STORY_VERSION,
        "animation_schema_version": contract.EXTENDED_SCHEMA_VERSION,
        "language": script.get("language") or "fr",
        "duration_target_s": duration_target_s,
        "narrator": dict(narrator),
        "characters": [dict(c) for c in characters],
        "shots": shots,
    }
    if editorial is not None:
        story["editorial"] = editorial
    if style_id:
        story["style_id"] = style_id
    if music_id:
        story["music_id"] = music_id

    errors = contract.validate_animation_story(story, catalog if catalog is not None else pipeline.RIG_V1_CATALOG)
    report = retention.analyze(script)
    issues = [{"section": i.get("section"), "code": i.get("code"), "severity": i.get("severity"), "message": i.get("message")}
              for i in report.get("issues", []) if i.get("severity") in ("high", "medium", "warning")]
    return AdaptResult({"content_format": "story", "title": script["title"], "story": story}, errors, issues)
