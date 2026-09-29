"""Deterministic, style-aware motion selection — Phase 2 of the Visual
Director roadmap. Replaces the old `block_index % len(_KB_MOVES)` rotation
in `engine/video.py` with a small rule system driven by the resolved
style's MotionProfile plus Phase 1's `shotType`/`visualPurpose`.

No new AI call, no new provider, no new ffmpeg filter: every profile is a
curated subset/ordering of the 6 Ken Burns moves `engine/video.py` already
implements (`_KB_MOVES`). This module only decides WHICH of those moves a
given shot gets — the moves themselves, and the render pipeline, are
untouched.

Determinism: `select_motion` hashes its inputs (style, block index, shotType,
visualPurpose, visual text) — same script, same output, every render. No
randomness.
"""
from __future__ import annotations

import hashlib
from collections import Counter

# Every name here must be one of engine.video._KB_MOVES ("in", "out",
# "right", "left", "up", "in_slow") — this module never invents a new camera
# move, it only curates which of the existing ones a style may use.
MOTION_PROFILES: dict[str, tuple[str, ...]] = {
    "cinematic": ("in_slow", "out", "left", "right", "up"),
    "gentle": ("in_slow", "left", "right"),
    "energetic": ("in", "up", "left", "right"),
    "comic": ("in", "up", "left", "right"),
    # "kinetic" : rendu par engine/motion_graphics ou la typographie
    # cinétique (engine/kinetic_typography.py), jamais de Ken Burns.
    "kinetic": (),
    # "none" : mouvement quasi nul, pour un style qui doit rester très calme
    # (ou n'a pas de mouvement de caméra propre, ex. stock footage).
    "none": ("in_slow",),
}
DEFAULT_PROFILE = "cinematic"

# shotType (Phase 1) : réduit le choix à un sous-ensemble plus adapté avant
# le hash — jamais en dehors du profil (voir _narrow). Absent de ce dict ==
# aucune préférence ("medium", ou tout autre shotType).
_SHOT_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "close_up": ("in_slow",),
    "wide": ("left", "right", "up", "out"),
    "insert": ("in", "in_slow"),
    "pov": ("in_slow",),
}

# visualPurpose (Phase 1) : indice supplémentaire, appliqué APRÈS le
# shotType. Absent de ce dict == aucune préférence.
_VISUAL_PURPOSE_HINTS: dict[str, tuple[str, ...]] = {
    "hook": ("in",),
    "establish": ("in_slow", "left", "right"),
    "reaction": ("in",),
    "reveal": ("in",),
    "payoff": ("in",),
    "cta": ("in_slow",),
}


def resolve_motion_profile(visual_style_id: str | None) -> str:
    """Repli sûr sur `DEFAULT_PROFILE` pour tout id inconnu — un ancien
    script, un id legacy non mappé, ou une phrase libre côté CLI se comporte
    comme avant (rotation Ken Burns classique sur le profil cinématique,
    proche du jeu de mouvements historique)."""
    from . import image_style_bible

    return image_style_bible.motion_profile_for(visual_style_id) or DEFAULT_PROFILE


def _narrow(candidates: tuple[str, ...], hint: tuple[str, ...]) -> tuple[str, ...]:
    narrowed = tuple(m for m in candidates if m in hint)
    return narrowed or candidates  # jamais un sous-ensemble vide : repli sur ce qui précède


def select_motion(
    profile: str,
    block_index: int,
    shot_type: str | None = None,
    visual_purpose: str | None = None,
    visual_text: str = "",
    previous_move: str | None = None,
) -> str:
    """Un mouvement Ken Burns pour un plan donné — déterministe (mêmes
    entrées, même sortie, rendu reproductible). `previous_move` : mouvement
    du plan immédiatement précédent dans la vidéo finale, pour éviter une
    répétition immédiate quand une alternative existe dans le même
    sous-ensemble (jamais en dehors du profil)."""
    # `.get(profile) or default` serait faux ici : "kinetic" est une clé
    # PRÉSENTE dont la valeur est délibérément `()` (pas de Ken Burns), à
    # distinguer d'un id de profil réellement inconnu.
    moves = MOTION_PROFILES[profile] if profile in MOTION_PROFILES else MOTION_PROFILES[DEFAULT_PROFILE]
    if not moves:
        return "in_slow"  # profil "kinetic"/"none" vide : ne devrait jamais être appelé (pas de Ken Burns), repli sûr

    candidates = moves
    if shot_type in _SHOT_TYPE_HINTS:
        candidates = _narrow(candidates, _SHOT_TYPE_HINTS[shot_type])
    if visual_purpose in _VISUAL_PURPOSE_HINTS:
        candidates = _narrow(candidates, _VISUAL_PURPOSE_HINTS[visual_purpose])

    seed = f"{profile}|{block_index}|{shot_type or ''}|{visual_purpose or ''}|{visual_text}"
    digest = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16)
    choice = candidates[digest % len(candidates)]

    if choice == previous_move and len(candidates) > 1:
        alternatives = tuple(m for m in candidates if m != previous_move)
        choice = alternatives[digest % len(alternatives)]
    return choice


def resolve_motion_sequence(
    shots: list[tuple[int, str | None, float, float]],
    blocks: list[dict],
    profile: str,
    video_extensions: tuple[str, ...] = (".mp4", ".mov", ".webm", ".m4v"),
) -> list[str | None]:
    """One motion (or `None`) per shot, in `engine.video.plan_shots` order.

    `None` for a shot with no image (flat color), a video source (stock
    footage or Motion Graphics — their motion is native, never Ken Burns —
    see PRODUCT context, section 2), or when the resolved profile is
    "kinetic"/empty. Computed strictly SEQUENTIALLY (not inside the render
    thread pool) so the "avoid immediate repeat" rule stays deterministic
    regardless of which clip's ffmpeg process finishes first."""
    moves = MOTION_PROFILES[profile] if profile in MOTION_PROFILES else MOTION_PROFILES[DEFAULT_PROFILE]
    resolved: list[str | None] = []
    previous_move: str | None = None
    if not moves:
        return [None] * len(shots)
    for block_index, image_path, _duration, _offset in shots:
        is_image = bool(image_path) and not image_path.lower().endswith(video_extensions)
        if not is_image:
            resolved.append(None)
            continue
        block = blocks[block_index - 1] if 0 <= block_index - 1 < len(blocks) else {}
        shot_type = block.get("shotType")
        visual_purpose = block.get("visualPurpose")
        visual_text = str(block.get("visual") or block.get("text") or "")
        move = select_motion(profile, block_index, shot_type, visual_purpose, visual_text, previous_move)
        previous_move = move
        resolved.append(move)
    return resolved


def _collapse_by_block(moves: list[str | None], shots: list[tuple[int, str | None, float, float]]) -> list[str | None]:
    """One motion per LOGICAL BLOCK, not per shot (Phase 2.6, benchmark fix).

    `engine.video.plan_shots` splits any block whose voiceover exceeds 3s
    into several sub-shots sharing the same `block_index` — `select_motion`
    legitimately holds the SAME move across them (see its own docstring: a
    single held camera move across a re-cropped sub-shot sequence is a valid
    choice, not a diversity failure). Analyzing the raw per-shot list treated
    every such split block as several "repeated motion" violations — the
    benchmark's `A/cinematic_real` run reported the same warning 5 times off
    a single split hook block. Collapsing consecutive shots that share a
    `block_index` into one entry BEFORE the diversity checks run fixes this
    without changing motion SELECTION at all."""
    collapsed: list[str | None] = []
    last_block_index: int | None = None
    for (block_index, *_rest), move in zip(shots, moves):
        if block_index == last_block_index:
            continue
        collapsed.append(move)
        last_block_index = block_index
    return collapsed


def analyze_motion_diversity(
    moves: list[str | None],
    shots: list[tuple[int, str | None, float, float]] | None = None,
) -> dict:
    """Deterministic, non-AI signal for `engine.quality.score_generation` —
    same "available/issues" shape as `engine.shot_planning.analyze_shot_diversity`.
    `available: False` (no penalty, no issue) when there is nothing to
    analyze: no image-backed shot at all (flat color, stock footage, Motion
    Graphics, or a "kinetic"/"none" profile) — the old, motion-free behavior
    for those cases is unaffected.

    `shots` (the same list `resolve_motion_sequence` was given, i.e.
    `engine.video.plan_shots`'s output) : when provided, consecutive shots
    sharing one `block_index` are collapsed to a single logical decision
    before analysis — see `_collapse_by_block`. Omitted only by tests that
    want the old flat-per-shot behavior directly."""
    per_block = _collapse_by_block(moves, shots) if shots is not None else moves
    typed = [m for m in per_block if m]
    if not typed:
        return {"available": False, "issues": []}

    issues: list[str] = []
    for prev, cur in zip(typed, typed[1:]):
        if cur == prev:
            issues.append(f"mouvement '{cur}' répété sur deux plans consécutifs")

    total = len(typed)
    if total >= 4:
        counts = Counter(typed)
        dominant_move, dominant_count = counts.most_common(1)[0]
        if dominant_count / total > 0.7:
            issues.append(f"mouvement '{dominant_move}' domine ({dominant_count}/{total} plans)")

    return {"available": True, "issues": issues}
