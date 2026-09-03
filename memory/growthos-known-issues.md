---
name: growthos-known-issues
description: Concrete defects and rough edges identified in GrowthOS during the 2026-09-03 review
metadata:
  type: project
---

Issues found reviewing GrowthOS on 2026-09-03. Items 1-4 + 6 fixed the same day.
Committed as `bdcdfcf` and pushed to branch **`growthos/mvp`** (renamed from
`claude/project-feedback-scs61n`). GrowthOS lives on its own branch — no PR, not
merged into the FI Validator's `claude/fi-validator-rag-ksdjI`.

1. **[FIXED]** ffmpeg subtitles path broke on Windows — `engine/video.py` `render_final()` now runs ffmpeg with `cwd` set to the `.srt` folder and references it by bare name, plus a `_run()` helper that surfaces ffmpeg stderr and a clear "install ffmpeg" message.
2. **[FIXED]** Stale checklist — `engine/publish_pack.build_checklist()` now emits the `log_metrics.py <id> --mark-published` command instead of referencing the removed `metrics/suivi-hebdo.csv`. `write_pack()` / `build_checklist()` take an optional `content_item_id`; `assembler.run()` reordered so the Supabase write happens before the pack.
3. **[FIXED]** No retry/resume on ElevenLabs — `engine/tts.py` `synthesize()` retries network errors + HTTP 429/5xx with exponential backoff (3 attempts), fails fast on other 4xx. `assembler.run()` reuses per-block audio and the final video already present under `output/<slug>/`.
4. **[FIXED]** get_or_create race — `engine/repo.py` `get_or_create_account()` is now an `upsert` on the `(organization_id, platform, handle)` unique constraint. `get_or_create_organization()` stays select-then-insert on purpose (no unique constraint on `organizations.name`, and a global-unique org name would be wrong for real multi-tenant).
5. **[OPEN — deliberate]** RLS schema is currently dead code; everything runs via `get_service_client()`. Fine per the README until an auth UI exists.
6. **[FIXED]** Audio concat gaps — `engine/video.py` `concat_audio()` switched from the concat demuxer + `-c copy` to the concat *filter*, output `full.wav` (lossless) instead of `full.mp3`. `assembler.run()` updated to pass `full.wav`.

ffmpeg: **now installed** on the user's Windows machine (ffmpeg 9.0.1-full_build, verified 2026-09-03 in a later session — the earlier "not installed" note is obsolete). The video half of the pipeline can now be run locally; a real ElevenLabs call still needs a valid key + voice_id in `.env` (currently `.env` == `.env.example`, placeholders only). Pure-logic unit tests: 24 pass.

Fixed in the 2026-09-03 follow-up (branch `claude/project-feedback-scs61n`, `corrige` pass; 27 tests pass, video path smoke-tested end-to-end with synthetic audio):
- assembler reuse restructured: if `final/<slug>.mp4` + `captions.srt` both exist, the run skips ElevenLabs and ffmpeg entirely; otherwise per-block audio and `full.wav` are each guarded by `_exists_nonempty` before regeneration. No more ffprobe-before-reuse crash.
- `aspect_ratio` now validated in `engine/script.validate_script` against `ALLOWED_ASPECT_RATIOS` (`9:16`/`1:1`/`16:9`), same pattern as `platform`.
- `slug()` falls back to `"script"` when title+account have no alphanumerics (was writing into `output/` root).
- `engine/video.render_final` takes a `font` arg / `SUBTITLE_FONT` env var, default `Arial` (libass silently substitutes if absent — Linux/CI).

Security review of the branch (2026-09-03, `/security-review`): **0 exploitable findings** — the branch is mostly hardening. Follow-up hygiene applied: `requirements.txt` pinned to `==`; a dependency-free `pre-commit` hook (`growthos/scripts/githooks/pre-commit`, installed via `growthos/scripts/install-git-hooks.sh` which sets repo-wide `core.hooksPath`) blocks committing a Supabase `service_role` JWT / populated `SUPABASE_SERVICE_ROLE_KEY` / `ELEVENLABS_API_KEY` / `.env` file in changes touching `growthos/`. `growthos/.gitattributes` forces LF on the hook scripts.

Still open (need a product decision, not a code fix):
- `audit.events` is a headline schema feature but **nothing ever writes to it** — every pipeline run / metric log is an unaudited service_role mutation.
- Schema (8 migrations, ~10 tables, RLS everywhere) is far ahead of the code, which touches only 4 tables, always via service_role. `profiles`, `organization_members`, `strategies`, `insights`, `recommendations`, `credits_ledger`, `account_oauth_tokens` are unused.
- Auth linkage: `get_or_create_organization` creates orgs with no `organization_members` row → once auth/RLS is live a signed-in user sees nothing until linked. **Addressed:** `growthos/scripts/backfill_membership.py` (`--list` / `--email X --dry-run` / `--email X`) creates the `profiles` + `organization_members` (owner) rows for orphan orgs once the user exists in Supabase Auth. `content_items`/`content_performance` need no `organization_id` column — RLS resolves via `account_id → accounts.organization_id`.
- Monorepo: growthos shares git history with the FI Validator RAG (repo root) and faceless-kids-stories; consider splitting it out once the loop is validated.
