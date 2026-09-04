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

**Visuels par bloc (2026-09-04, `103b88d`)** : l'utilisateur a comparé le produit à facelessreels.com et pointé deux trous — tout est manuel, et les vidéos n'ont aucun visuel (fond couleur unie fixe). Réponse en deux temps : (1) plan priorisé donné à l'utilisateur (visuel d'abord, puis réduire les clics/assistance IA scripting, puis publication auto — délai d'approbation OAuth TikTok/Meta à lancer en parallèle si voulu) ; (2) le visuel est codé — `engine/visuals.py` (Pexels, gratuit, clé demandée à l'utilisateur) + `engine/video.py` réécrit pour un clip Ken Burns par bloc au lieu d'un fond fixe unique. Chemin de repli (sans image) vérifié en réel end-to-end à travers la nouvelle mécanique. **[VALIDÉ 2026-09-04, `00f8d72`]** Testé en réel avec une vraie clé Pexels (fournie par l'utilisateur, ajoutée à `.env`) : 4/4 images trouvées et téléchargées, vidéo rendue avec Ken Burns + sous-titres, uploadée sur Storage, URL publique fetchable. Frame extraite envoyée à l'utilisateur (`SendUserFile`) pour vérification visuelle — rendu correct (image plein cadre, sous-titres lisibles en bas). Ajusté après coup : "voici" et quelques marqueurs de discours polluaient les mots-clés de recherche, ajoutés aux stop-words.

**Point de polish repéré, pas corrigé** : sur un bloc au texte long (4 lignes de sous-titres), le texte recouvre une bonne partie du cadre — plus visible maintenant qu'il y a une vraie photo derrière (sur l'ancien fond uni ça ne se remarquait pas). Pas grave, mais à revisiter (raccourcir les blocs recommandés, ou réduire `FontSize`/ajuster `MarginV` selon le nombre de lignes).

Performance (2026-09-04, `557513a`) : la voix off ElevenLabs tournait en boucle séquentielle par bloc — parallélisée (`ThreadPoolExecutor`, 4 en simultané, ordre préservé et vérifié par smoke test réel à 5 blocs). Rendu ffmpeg final passé en `-preset veryfast -tune stillimage` (fond uni fixe, seuls les sous-titres bougent — cas d'usage exact de ce tuning). Mesuré : 1 bloc ≈ 5 blocs ≈ 13s, contre un temps qui scalait avec le nombre de blocs avant. Levier non pris (trade-off qualité, décision utilisateur) : passer `eleven_multilingual_v2` à un modèle ElevenLabs plus rapide (`eleven_flash_v2_5`/`eleven_turbo_v2_5`) — latence par appel bien plus basse, voix légèrement différente.

**[RÉSOLU 2026-09-04, `f3c0e85`]** Stockage vidéo : bucket Supabase Storage public `content-videos` (`<content_item_id>.mp4`, upsert). `engine/storage.py` `upload_video()` appelé depuis `assembler._publish_video()` dans les deux points d'entrée (`run()` et `run_for_content_item()`) — `video_url` est maintenant l'URL publique Storage, avec repli sur le chemin local si l'upload échoue (pas d'échec du run pour autant). Écriture réservée à service_role (pas de policy RLS à écrire, seul le worker y touche). Vérifié en réel : upload + URL publique fetchable (HTTP 200, bon content-type/taille). Les 2 vidéos générées avant ce changement ont été backfillées.

Still open (need a product decision, not a code fix):
- `audit.events` is a headline schema feature but **nothing ever writes to it** — every pipeline run / metric log is an unaudited service_role mutation.
- Schema (8 migrations, ~10 tables, RLS everywhere) is far ahead of the code, which touches only 4 tables, always via service_role. `profiles`, `organization_members`, `strategies`, `insights`, `recommendations`, `credits_ledger`, `account_oauth_tokens` are unused.
- Auth linkage: `get_or_create_organization` creates orgs with no `organization_members` row → once auth/RLS is live a signed-in user sees nothing until linked. **Addressed:** `growthos/scripts/backfill_membership.py` (`--list` / `--email X --dry-run` / `--email X`) creates the `profiles` + `organization_members` (owner) rows for orphan orgs once the user exists in Supabase Auth. `content_items`/`content_performance` need no `organization_id` column — RLS resolves via `account_id → accounts.organization_id`.
- Monorepo: growthos shares git history with the FI Validator RAG (repo root) and faceless-kids-stories; consider splitting it out once the loop is validated.
