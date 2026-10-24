# Story Studio — Animation Recovery Contract (v1)

Status: PROPOSED / NO-GO for production. Owner: Faceloop product and engineering. Reference scenario: **Influence mentale**.

## Product promise
Story Studio produces actual animated dramatic scenes, not static illustrations with narration, Ken Burns, pan/zoom, or motion typography. A story video contains recognizable recurring characters that visibly act and react to one another.

## Reference acceptance test: Influence mentale (20 seconds, vertical 9:16)
Two identifiable characters A and B in one environment, at least 3 connected shots:
1. A speaks and gestures while B listens and visibly reacts.
2. A leans forward / changes expression; camera reframes; B hesitates.
3. B steps back, changes facial expression, and responds.

Acceptance evidence: inspect actual rendered MP4 frames and audio, not prompts, mocks, stills, or green unit tests alone.

## Mandatory gates
- G0: Inventory current backend, frontend, providers, storage, queues, tenant isolation, billing and rendering. Document verified file paths and integration points.
- G1: Provider spike: generate real subject motion (not animated stills); measure failure rate, latency and cost per accepted second; get explicit approval before paid calls.
- G2: Character continuity: recognizable identities, clothing, and scene consistency across shots. Document observed failures and retries.
- G3: Audio: correct speaker assignment, measurable dialogue timing, lip-sync where feasible, audible reactions; do not claim sync without watching the output.
- G4: MP4 export: vertical 9:16, audio/video playback, stable duration, no frozen or duplicated frames, reproducible asset provenance.
- G5: Safety and operational controls: credits before spend, strict org scoping, idempotent jobs, retries with caps, rate limits, cleanup, observability and no secret logging.
- G6: Product UI only after G1-G4: director controls, timeline, preview and targeted shot regeneration.

## Data contract proposal (not yet implemented)
Story -> CharacterBible (immutable identity/reference assets) -> ShotPlan[] (speaker, dialogue, on-screen action, emotional state, camera, duration, visual references) -> AnimatedClip[] (provider, input asset hashes, output video URI, duration, verification state) -> AudioTrack[] -> FinalMP4.
Every shot must specify visible action; narration-only or image-only assets cannot be labeled animated clips.

## Findings verified in repository
- `growthos/engine/story_compile.py`: current story compiler maps one shot to one dialogue block and an illustrated character visual; estimate assumes one image per shot. It explicitly says it is not connected to `script.normalize_script`.
- `growthos/engine/story_intelligence/timing.py`: offline duration alignment using caller-supplied audio measurements; no video or TTS generation.
- Frontend `growthos-web/src/lib/story-studio/render.ts`: estimate reports images per shot; no animated clip estimate.
- Frontend `growthos-web/src/app/(app)/story-studio/actions.ts`: queue behind `STORY_GENERATION_ENABLED`, platform-admin gate and paid confirmation.

These findings are not a complete inventory of every other video integration. Do not assert absence of a provider until inventory is finished.

## First implementation PR (future, separate)
Provider-neutral `AnimatedShot` schema, validation, and isolated offline tests. No changes to Standard/Quiz. No live provider call until approved cost/quality test.

## Definition of done
A reviewer can watch an actual 20-second MP4 meeting the three scene actions above, verify stable characters, hear dialogue, and inspect generation cost and failures. Otherwise Story Studio remains experimental, not shipped.

## Non-goals
No UI-only redesign, no fake animated preview, no silent migration, no production flag enablement, no external paid generation without approval.
