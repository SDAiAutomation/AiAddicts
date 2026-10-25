# Story Studio — Facial Performance Spike (read-only audit + implementation plan)
Date: 2026-10-25
Branch: feature/story-facial-performance-spike-20261025
Status: specification only; no production renderer change, no API charges, no claim of rendered validation.

## Verified baseline
Source: `growthos/engine/story_animation/godot/rig_v1/scene.gd` on `growthos/mvp`.
- Existing puppet rig for Pip and Rosette with per-character anchors and separated sprite elements.
- `MOODS` already defines neutral, worry, angry, surprise, joy, puzzled, panic.
- `draw_face` draws eyes, brows and mouth; `blink_amt` uses periodic frame-based blinking.
- `mouth_of` reads c/o/r per-frame mouth characters from measured audio timeline.
- `draw_face` interpolates facial properties with fixed 0.3 per-frame factor.
- `gaze` and `mood` are already pose parameters.
- Therefore do NOT add duplicate emotion enums or replace the existing renderer without evidence.

## Observed gaps / risks to verify in a real render
1. Mouth shapes c/o/r are not phoneme/viseme alignment; audio envelope alone cannot guarantee intelligible lip sync.
2. Blink is periodic rather than contextual; can occur during emotionally inappropriate moments.
3. Face smoothing is frame-dependent and uses mutable state; verify deterministic render/restart behavior.
4. Unknown mood indexes `MOODS[mood]` directly; validate timeline values or safely fall back to neutral.
5. Character-specific face geometry is currently procedural and coupled to Pip/Rosette; assess generalization.
6. No proof here of artistic quality or end-to-end production readiness.

## Minimal implementation sequence (behind opt-in flag)
1. Add bounded, schema-validated facial cues per shot: `emotion`, `gaze`, `blink`, `mouth_track`. Preserve legacy `mood` and c/o/r track.
2. Add deterministic blink scheduling with optional intentional cue; no RNG and no API calls.
3. Implement a pluggable viseme track interface, defaulting to existing c/o/r if no aligned track exists. First prove with a manually aligned 10-second test; do not purchase a speech model.
4. Replace per-frame fixed interpolation with time-based smoothing while preserving existing visual behavior as fallback.
5. Test 10-second single-character performance: neutral -> worry -> surprise, spoken dialogue, eye direction and deliberate blink.
6. Only after acceptance test two-character dialogue and renderer integration.

## Acceptance gates
- Test input and output deterministic for identical assets/timeline.
- No exceptions on unknown emotion; neutral fallback and logged warning.
- No mouth movement during silence; mouth shapes correspond to spoken intervals.
- Visible emotions readable at phone size; no facial jitter or geometry jumps.
- No modifications to Standard Video or Quiz, no production flag enabled.
- Track: render duration, CPU/GPU runtime, generated asset count, cost per accepted 10-second shot.
- Human review of exported MP4 is mandatory; automated tests alone are not a pass.

## Stop conditions
- If rig is not visually convincing in 10 seconds, stop integration and compare alternate 2D puppet approaches.
- Do not expand to 90-second stories, cloud rendering, paid video models, or frontend rollout until benchmark passes.
