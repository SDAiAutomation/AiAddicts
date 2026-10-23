# Faceloop WOW — P0 technical audit (2026-10-23)

## Scope and method
Read-only inspection of known Python engine files on base branch `growthos/mvp`. No tests run and no production configuration inspected. This is a **partial dependency audit**, not a full security or frontend review.

## Verified reuse map
| Base module | Observed capability | Reuse decision |
|---|---|---|
| `growthos/engine/assembler.py` | Central `_generate`, `run`, `run_for_content_item`, publishes video and computes cost | Do not change for POC; inspect call graph before later integration |
| `growthos/engine/asset_store.py` | `content-assets` private bucket, `content_assets` table, content-item-scoped manifest, voice and image cache | Reuse concept; verify tenant scoping and cross-job asset ownership before integrating |
| `growthos/engine/tts.py` | ElevenLabs voice generation, with-timestamps word alignment, media duration | Reuse via adapter; timestamps are **not** phoneme-level lip sync |
| `growthos/engine/video.py` | FFmpeg block clips, camera moves, final render, 9:16 resolution | Reuse output conventions; avoid modifying legacy renderer for POC |
| `growthos/engine/captions.py` | SRT/ASS, animated subtitles, vertical safe zones | Reuse captions after timing adapter |
| `growthos/engine/quality.py` | Existing quality gate, generic shot-duration limits | New style-specific policy needed; do not weaken existing QA |
| `growthos/engine/shot_planning.py` | Deterministic shot diversity checks | Reuse framing concepts; new schema adapter required |
| `growthos/engine/storage.py` | Private `content-videos` bucket, versioned video upload | Future integration only after auth review |
| `growthos/engine/db.py` | anon client vs service-role client | Never expose service role to end-user paths |
| `growthos/engine/generation_cache.py` | Code+script fingerprint | Add new animation module fingerprints only when feature integrated; avoid stale cache |
| `growthos/engine/events.py` | Nonblocking generation event/cost tracking | Useful, but nonblocking events alone are **not** a hard spending cap |

## Critical risks
1. **Budget enforcement:** estimated costs and nonblocking analytics do not guarantee a spending ceiling. Add transactional reservation / atomic quota checks before each paid provider request.
2. **Tenant security:** current cache manifest is content-item-scoped; independently verify server-side ownership checks and storage policies before reuse.
3. **Visual quality:** existing camera motion and subtitles do not equal character animation. Rigging, mouth visemes, facial expressions and continuity are new.
4. **Timing:** ElevenLabs word timestamps cannot alone generate precise visemes. Evaluate phoneme alignment or a bounded approximate fallback, clearly labeled.
5. **Quality gate:** the existing maximum shot duration and reach thresholds may be inappropriate for acting scenes. New gate must not change legacy defaults.
6. **Idempotency:** current file-based reuse helps, but distributed retries require job identity and verified completed artifacts.
7. **Versioning:** add code/rig/voice/reference revisions to new cache keys and never share assets across tenants without authorization.

## Base branch vs existing experimental PR
The files `animated_story.py`, `animated_story_plan.py` and `animated_story_executor.py` are present only on draft PR #62, not on `growthos/mvp`. That branch's tests are not known to have run. Reassess its paid-provider-oriented executor against the **zero-paid-video-API** strategy before reuse.

## P0 gaps still to audit
- Actual web frontend route/format registry and schema validation.
- Job queue, worker concurrency, cancellation and deployment topology.
- Supabase policies, user/organization ownership and upload authorization.
- Test discovery and CI workflow on the correct paths.
- FFmpeg runtime environment, codecs, performance and local GPU availability.
- License compatibility for candidate lip-sync and rigging libraries.
- Existing billing/credit ledger and whether reservations are atomic.

## P1 proposed safe deliverable
Create a **standalone local-only** `animated_microdrama` prototype on a new feature branch, with:
- original/licensed character layer assets and a rig manifest;
- a deterministic timeline for blinking, expressions, head/arm motion and parallax;
- offline placeholder dialogue/audio (no paid API) and captions;
- FFmpeg MP4 9:16 export;
- 15–20 second pilot and render-time benchmark;
- automated unit and smoke tests.
No changes to `assembler.py`, existing routes, tables, billing, deployment or existing formats. No publishing.

## Go/no-go after P1
Only extend to 30–45 seconds if visual review confirms recognizable characters, acceptable acting and lips, complete render, repeatability and measured marginal cost. Otherwise stop or iterate within the agreed time box.
