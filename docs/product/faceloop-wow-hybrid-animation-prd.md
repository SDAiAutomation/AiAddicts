# Faceloop WOW — Hybrid Animation First
**Product decision record & execution charter** | 2026-10-23 | Status: PROPOSED / discovery approved, production NOT approved

## Executive decision
Pursue a **time-boxed, low-cost 2D/2.5D animated microdrama proof of concept**. Do not build a full animation platform, buy additional subscriptions, modify legacy formats, or deploy anything until the pilot proves value. The business objective is **higher perceived video quality and creator retention at sustainable marginal cost**; the technical objective is **reuse over repeated generative-video API calls**.

Faceloop's current value proposition (Stories, Quiz, Motion Graphics, existing video workflows) is protected. The new format is additive, opt-in and behind a disabled-by-default feature flag.

## Business case and falsifiable hypotheses
1. Original recurring characters, sets and voices may increase creator retention and series creation compared with one-off Shorts. **Not yet demonstrated.**
2. Reusing rigged assets and deterministic animation may reduce variable generation cost compared with paid text-to-video for every second. **Compute, development and asset-creation costs still count.**
3. Strong scripts, framing, sound and facial acting may outperform generic slideshow-like videos. **Quality must be judged blindly.**
4. Users may pay for consistent character-based series. **Willingness to pay is unvalidated.**

Do not equate platform-level microdrama view counts with demand for Faceloop, or assert which private tools a TikTok creator uses from a screenshot.

## Product scope
**MVP:** One 15–20s animated scene, two original recurring characters, one setting, distinct voices, 3–5 shots, visible emotion, basic mouth shapes and subtitles. Then extend to a 30–45s episode (6–10 shots) only if the first pilot passes.
**Later:** Cinematic Mystery and Character-led Explainer as format variants; premium generated hero shots only when a measured quality gain justifies cost.
**Not in MVP:** 3D cinematic full-body animation, unlimited character generation, real-time editing, multi-provider paid routing, autopublishing, a new SaaS subscription or new persistent infrastructure.

## Existing investment: reuse before buy
- OpenAI/Claude already paid for: storyboard, dialogue, continuity planning. Limit redundant LLM calls; prefer one structured generation plus deterministic checks.
- ElevenLabs: existing voices, per-character reuse, timestamps where supported; avoid resynthesizing identical speech.
- Python, Pillow and FFmpeg: 2D/2.5D compositing, puppet transforms, camera moves, scene assembly, subtitles.
- Supabase: existing storage and database, subject to tenant isolation, quotas and actual consumption.
- Vercel: existing frontend, only after pipeline viability.
- Investigate Rhubarb Lip Sync and other open-source tools; confirm licenses, packaging and platform support before adopting.

## Proposed architecture (separate, no legacy changes)
`new animated_microdrama format (feature flag OFF)`
→ script + character bible + storyboard
→ versioned character sheet and reusable rig (body, head, eyes, brows, mouth visemes, arms)
→ dialogue with voice timestamps / optional phoneme extraction
→ deterministic shot animator (expression, head turns, blink, pose, camera, parallax)
→ compositing + captions + audio with existing FFmpeg
→ automated QA + human review
→ local MP4 pilot
→ optional Studio integration, only after approval.

Use a provider abstraction so a future paid animation engine can be plugged in without refactoring the core. The default path must require **zero paid video-generation calls**. No unsupported assumption that voice timestamps alone provide accurate phoneme lip-sync.

## Costs and financial controls
**No new subscriptions** during POC. **No paid external video model calls** in POC. Existing LLM and TTS calls must be counted, not considered free merely because a subscription exists.
- Require cost estimates before execution and actual spend logs by video, shot, provider and tenant.
- Enforce per-job spending ceiling and server-side pre-call budget checks. Abort rather than silently exceed.
- Cache by versioned assets, text, voice/model/settings, rig, render parameters and tenant.
- Track CPU/GPU time, retries, storage and egress; report both marginal cash spend and amortized asset-creation cost.
- Provisional target: **under $0.50 variable cash cost per 30–45s video**, excluding fixed development and infrastructure, to be tested rather than promised.
- Compare against the current Stories format on equivalent script length and production quality.

## Experiment design and stop/go gates
**Time box:** up to 2 weeks of focused engineering effort for POC; not a delivery-time guarantee.
**Stage A:** 15–20s local MP4; two original characters, one setting, 3–5 shots, dialogue, mouth animation, captions.
**Stage B:** only after A passes, 30–45s episode with 6–10 shots, reuse of the same character rigs in 3+ scenes.
**Stage C:** compare with existing Faceloop Stories on identical narrative; blind quality panel (multiple evaluators) and measured cost.

Proposed acceptance criteria:
- Visual/story/audio quality average >= 4/5 from blind evaluators, with no critical identity or sync failure.
- End-to-end processing < 10 minutes per 30–45s episode on documented hardware (target, not guarantee).
- Marginal cash spend < $0.50 per video, with full cost accounting disclosure.
- Same character is recognizably consistent across >= 3 scenes.
- Existing format regression tests pass; no production route modified.
- Tenant authorization, asset ownership, cancellation and failure handling reviewed before SaaS rollout.

**NO-GO / pivot:** quality below threshold after time box, unacceptable rigidity, cost target missed, or disproportionate engineering maintenance. Then prioritize improving existing video formats instead of expanding animation engine.

## Implementation plan
### P0 — Discovery and baseline
Audit `growthos/engine` orchestration, FFmpeg and ElevenLabs functions, asset store/cache, job workers, Supabase tenancy/storage, frontend format registry, CI and tests. Record a dependency map and existing-format baseline. Do not change existing code.
### P1 — Rig proof of concept
Build standalone character schema, reference art import, separate eyes/mouth/arms/head layers, expression keyframes, deterministic animation timeline and a short MP4 fixture. Use original/licensed art only.
### P2 — Voice and lip-sync
Reuse existing ElevenLabs interface; evaluate phoneme/viseme extraction; cache audio and alignment; enforce voice-first shot timing. Test silence, punctuation and French/English.
### P3 — Film-quality compositing
Implement reusable sets, parallax, camera language, scene transitions, sound design and subtitles. Produce a complete 15–20s pilot and evaluate.
### P4 — Cost/quality benchmark
Measure render duration, variable API cost, CPU/GPU, asset reuse and storage. Blindly compare with Stories. Decide GO / ITERATE / STOP.
### P5 — Optional beta
Only if P4 passes: new format in Studio behind OFF-by-default flag, per-tenant access checks, budget controls, human approval and rollback. No auto-publication.

## Repository and PR boundaries
This is a **documentation-only decision PR** branched from `growthos/mvp`. It does not merge or replace the earlier experimental draft PR #62 (`feat/animated-story-engine-prototype`), which contains initial contracts, planning, injected renderer and unexecuted tests. Reassess that prototype against this lower-cost architecture before reuse. Do not merge #62 as-is without test execution and a demonstrated pilot.

## Definition of done for current PR
- Strategy, scope, cost controls, acceptance gates and rollback criteria documented.
- Zero changes to executable code, dependencies, API routes, database schema or current formats.
- Product owner reviews and approves direction before implementation begins.

## Immediate next engineering task
Conduct the P0 dependency audit, then build a local, zero-paid-video-provider 15–20s prototype on a **separate feature branch**. Record evidence, actual costs and quality limitations before proposing integration.
