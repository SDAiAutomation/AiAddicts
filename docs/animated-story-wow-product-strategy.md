# Faceloop WOW — Product strategy and delivery gates (2026-10-23)

## Product mandate
Ship a new, **optional** Animated Microdrama format that creates emotionally compelling, coherent, original character-led videos. Do not modify existing Quiz, Stories, Motion Graphics, publishing, or billing paths. Default feature flag OFF. No deployment, production API calls, or merge without CI and approval.

## Evidence versus hypotheses
YouTube reported over 6.5B microdrama views in H1 2026 and >50% YoY watch-time growth; this is a category signal, not proof that any particular AI channel succeeds. Audience retention must be measured using video-level YouTube Analytics. The screenshot of Influence Mentale does not establish which video models it uses; avoid claiming its stack is known.

Primary sources:
- https://blog.google/intl/en-in/products/platforms/connect-with-creators-on-the-biggest-screen-with-youtubes-latest-features/
- https://support.google.com/youtube/answer/9314415
- https://docs.dev.runwayml.com/guides/models/
- https://dev.runway.com/pricing
- https://www.hedra.com/develop/models/video
- https://www.hedra.com/develop/models/video/hedra-character-3
- https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two

## Product formats and ranking
1. Animated Microdrama (MVP): original recurring characters, conflict, emotional stakes, twist, payoff; 30–45s pilot.
2. Cinematic Mystery: suspense, cinematic visuals, short narrative reveals.
3. Character-led Explainer: visual explanations by a consistent cast.
Ship only format 1 initially; other two remain roadmap candidates.

## Competitor / model benchmark
Do not infer a competitor's private stack from screenshots. Benchmark models against the SAME storyboard, reference character sheets and voice track:
- Kling 3.0 Standard: short image-to-video, published indicative $0.09/sec without audio via Runway API.
- Runway Gen-4.5: cinematic video, published indicative $0.12/sec.
- Veo 3.1 Fast: published indicative $0.10/sec without audio.
- Seedance 2.0 Mini: published indicative $0.07/sec at 480p, quality tradeoff.
- Hedra Character 3: audio-driven character video, indicative $0.05/sec at 720p.
- Runway Act-Two: performance transfer; single-character performance workflow needs extra compositing for conversations.
All pricing is time-sensitive, model-specific and excludes retries, voices, images and infrastructure. Confirm commercial rights, input limits, quotas and current pricing before use.

## Target pipeline
Story concept -> story editor -> script/retention -> character bible -> reference assets -> shot storyboard -> per-character ElevenLabs audio and word timestamps -> shot renderer router -> audio-driven talking shots or image-to-video action shots -> continuity QA -> FFmpeg assembly/captions -> human review -> optional publishing.

Use existing modules where feasible:
- growthos/engine/retention.py
- growthos/engine/shot_planning.py
- growthos/engine/tts.py
- growthos/engine/video.py
- growthos/engine/quality.py
New opt-in foundation in PR #62:
- animated_story.py
- animated_story_plan.py
- animated_story_executor.py

## Architecture rules
- Separate format registry and feature flag; no changes to existing defaults.
- Provider adapter interfaces, versioned prompt and reference assets, content hashes.
- Per-shot idempotency and cache with tenant scope, immutable assets and authorization.
- No unmetered paid calls; server-side cost caps and spending ledger.
- Job cancellation, bounded retries, circuit breakers, no silent fallback to unrelated images.
- No cloning identifiable characters or voices without permission.
- No automatic publishing until explicit human approval.
- Never treat a passing static validator as evidence of video quality.

## Creative quality bar
Two original recurring characters, one coherent world, distinct silhouettes, consistent clothing, shot-reverse-shot conversations, natural lip-sync, meaningful facial acting, audio-first timing, subtle sound design, polished captions, visually legible 9:16 framing, clear reveal, no AI-generated unreadable text.
Pilot: 30–45s, 6–10 shots, 2 voices, one location, 2–3 hero shots; use affordable still/puppet techniques for other shots.
Qualitative rubric (human panel): story clarity, emotional payoff, identity consistency, motion realism, lip-sync, sound, subtitles, novelty; each 1–5. No release with critical continuity or sync defects.

## Delivery phases and acceptance criteria
P0 Discovery: inspect assembler, asset_store, async jobs, database/storage tenancy, frontend format registration, QA and CI. Produce dependency map; no edits to legacy modules.
P1 Contracts (started): validate story, immutable render plan, budget estimates, testable injected render adapters.
P2 Reference assets: original character library, rights, reference versioning, isolation tests.
P3 Pilot pipeline: real voice timings, shot generation adapters, FFmpeg assembly and downloadable MP4, mocked integration tests.
P4 Quality and cost: actual cost ledger, retry policy, visual review queue, sync checks, regression suite.
P5 Studio integration: feature-flagged creation and review UI, opt-in beta.
P6 Controlled pilot: at least 3 full videos, measured actual cost, manual quality review, retention measurement after publication with user consent.

## Decision gates
GO to provider pilot only if credentials, provider rights, rate limits, security, budget and data handling reviewed.
GO to beta only if all existing format regression tests pass, pilot files verified, no cross-tenant leaks, costs bounded, and quality approved.
GO to production only after owner approval and monitoring/rollback are operational.

## Current status
Foundation and tests committed to draft PR #62; tests not confirmed executed; no actual video rendering or production integration has been demonstrated. Do not describe this as a finished feature.
