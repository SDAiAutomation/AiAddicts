---
name: active-project-growthos
description: The user is actively working on the GrowthOS sub-project within the AiAddicts monorepo
metadata:
  type: project
---

As of 2026-09-03 the user is working on **GrowthOS** (`growthos/` in the `AiAddicts` repo), not the FI Validator (repo root) or `faceless-kids-stories/`.

The `AiAddicts` repo is a monorepo of three unrelated projects sharing one git history. GrowthOS is an MVP "dogfooding" pipeline: `content/scripts/*.json` → ElevenLabs voiceover → ffmpeg text-card video with burned SRT captions → manual-publish pack (`caption.txt` + `checklist.md`). Persistence is a dedicated Supabase project `growthos` (ref `lclesqfokgetznhepgmj`, eu-west-1) with a full multi-tenant schema (orgs, roles, OAuth tokens, strategies, content pipeline, credits, append-only `audit.events`). All writes currently go through `service_role` — the RLS machinery is built ahead of any auth UI.

Entry points: `growthos/main.py <script.json> [--voice <id>]` (pipeline, creates a new content_item), `growthos/worker.py [--interval N] [--once]` (added 2026-09-04 — polls content_items in `status='queued'` inserted by the `growthos-web` frontend and generates their video via `engine/assembler.run_for_content_item()`, updating the existing row instead of creating one — see [[growthos-web-frontend]] for the job-queue flow), `growthos/log_metrics.py <content_item_id> ...` (weekly metrics). Tests: `python -m unittest discover -s tests` from `growthos/`, pure logic only (no network/ffmpeg) — 36 pass as of 2026-09-04.

Voice selection (added 2026-09-03): `voice_id` is no longer required in the script. Resolved at generation by `engine/voices.py` in order: `--voice` flag > script `voice_id` > `config/voices.json` keyed by `niche` > `config/voices.json` "default". The resolved voice is written back into the stored `content_items.script`. `engine/assembler.run()` gained a `voice_override` param. No interactive picker on purpose (pipeline stays scriptable).

Known issues surfaced in the initial analysis — see [[growthos-known-issues]].
