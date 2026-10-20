# Long Quiz 50 — delivery status and acceptance gates

Status: **implemented end to end, validated offline, NOT production approved** (see "Release decision").

## Product target
One landscape YouTube long-form quiz with 50 fact-checked questions in five named difficulty chapters
(Easy 1–10, Medium 11–20, Hard 21–30, Expert 31–40, Genius 41–50), plus five separately exportable vertical videos.

## What exists (backend, this repo)
| Area | Implementation | Evidence |
|---|---|---|
| Contract | `quiz.chapter_mode = five_levels` needs `recipe: long`, `difficulty: progressive`, exactly 50 questions; legacy mode unchanged | `tests/test_quiz.py`, `tests/test_quiz_chapters.py` |
| Chapter scenes | A narrated `chapter` block before questions 1/11/21/31/41 (Motion only, idempotent insertion, validated by `validate_motion_blocks`); five distinct animated identities (EASY bounce+confetti, MEDIUM slide+bars, HARD slam+flash, EXPERT drawn frame+tightening type, GENIUS cinema bars+rays) in 16:9 and 9:16 | `engine/quiz_motion.py::_chapter_scene`, rendered stills and full render (see below) |
| Timing | Scene timeline built from **decoded** audio durations. Container (header) durations of mp3 blocks include ~25 ms encoder delay each, which drifted a 107-block timeline by ~3 s | `tts.get_playback_duration_seconds`; sample master 706.073 s vs timeline 706.0731 s |
| Chapter planner | `quiz_chapter_export.chapter_segments` from measured scenes (cards optional but never partial) | `tests/test_quiz_chapter_export.py`, `tests/test_quiz_chapters.py` |
| Vertical exports | `engine/quiz_shorts.py`: real 9:16 Motion composition (`quiz_layout: short`), same narration/SFX audio as the master, chapter-relative progress bar, captions lifted clear of the platform UI zone, ffprobe validation (1080×1920, audio present, duration within 0.25 s), atomic publish, per-chapter failure isolation | `tests/test_quiz_shorts_render.py` (real FFmpeg), sample render |
| Duration policy | YouTube Shorts accept up to 3 min (**verify in YouTube Studio**: sources found are secondary). A chapter whose measured duration exceeds 178 s is split at a question boundary into the fewest balanced parts, each opening with the chapter card. Nothing is sped up or truncated; `short_eligible` is recorded per file | `partition`, `plan_exports` tests |
| Jobs | Additive migration `20261020180000_quiz_chapter_exports.sql`: table with RLS, RPC-only writes (editor+), idempotent request/retry (5 attempts), `skip locked` claim, stale-job reclaim, storage paths in a column `authenticated` cannot read; series constraint for five-level config | `supabase/tests/quiz_chapter_exports/run.sh` on a throwaway Postgres 16 (also in CI) |
| Worker | `engine/quiz_export_job.py`: restores narration from the asset cache (never synthesizes), rebuilds padded audio, renders, uploads under `<item>/shorts/v<n>/`, removes its private temp dir | `tests/test_quiz_export_job.py` |

## What exists (frontend, growthos-web)
Level-by-level generation (plan → 5 levels → finalize → blind verification) with named progress and per-level retry;
review by level with quality summary (verification, duplicates, difficulty calibration); tier-aware single-question
regeneration; exact-50 and duplicate gating; strict `chapter_mode` persistence; export panel with request, retry,
status polling, preview and signed download. See that repo's PR.

## Difficulty calibration
Prompts alone do not guarantee difficulty. Each level has explicit criteria (`src/lib/quiz-levels.ts`), used as the
generator instruction **and** as the grid for an independent blind rating (1–5) made by the verification model, which
does not know the intended level. `calibrationReport` flags questions rated ≥2 steps away from their level, answers
that are uniquely much longer than their distractors, and a non-increasing level progression. This is a review
signal, not proof of difficulty.

## Validation performed (this environment)
- Offline suites (see PR for commands and counts); migration replayed twice and exercised for RLS/idempotency.
- Full 50-question sample (`scripts/render_quiz50_sample.py`): 16:9 master 1920×1080 and five 1080×1920 exports, all
  validated by ffprobe, audio/video lengths within ~30 ms. **The narration in that sample is synthetic tone bursts**
  (no TTS provider is reachable here), so intelligibility and real-voice pacing are NOT validated.
- Stills of all five chapter cards inspected in both orientations; question/reveal frames inspected in both.

## Explicitly NOT validated
- A real 50-question render with ElevenLabs voice (cost, wall time, 45 min worker limit).
- Real OpenAI generation quality/cost for 50 questions (all provider calls are mocked in tests).
- The migration on a staging Supabase project; storage bucket policies in the real project.
- YouTube upload/playback of the exports; the current Shorts rules.
- Illustrated (`illustrations: true`) and `backdrops` quizzes in the vertical exports (text-only layout is used).
- A manual review of the whole wizard in the real application with real data.

## Release decision
Do not merge or deploy solely because these tests pass. Required before release: staging migration, one real
50-question run (voice + images off) with a human watching all five chapters and the exports, a YouTube playback check,
and a cost/time measurement.
