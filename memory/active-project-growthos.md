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

### Quiz vidéo (2026-09-20)

Le moteur Python accepte `content_format: "quiz"` avec recettes, questions, templates et effets sonores. Les questions sont compilées en blocs question/révélation au chargement; le frontend ne doit donc pas exiger `script.blocks` pour mettre un quiz en file. Templates : studio, arcade, education, sport, pop, minimal, photo, logo. Effets : automatic, subtle, off; FFmpeg place les bips après la narration, pendant `hold_after_seconds`. Les vidéos classiques restent sur leur pipeline visuel historique. État poussé sur `growthos/mvp` : commits `8a623f5`, `e05f57e`, `b8933e8`.

Le frontend quiz (`growthos-web/master`, `ed21f2c`) propose désormais catégorie, sujet facultatif et trois titres générés par IA. Le titre sélectionné reste éditable. La catégorie initialise aussi la couleur et le titre de couverture, sans modifier le pipeline des vidéos classiques. L'action de suggestion n'envoie à OpenAI que catégorie, sujet, recette et langue, avec contrôle du rôle et consommation du quota `quiz`.

### Faceloop doctrine et AutoEdit (2026-09-23)

La doctrine produit est documentée dans `growthos/PRODUCT_DOCTRINE.md`; les instructions partagées sont dans `growthos/AGENTS.md` et `growthos/CLAUDE.md`. Le produit possède deux moteurs : Generate (idée vers Short) et AutoEdit (rushes utilisateur vers Short). Claude Code possède le backend/worker/IA/média; Codex possède le frontend `growthos-web` et l'expérience utilisateur.

Le contrat AutoEdit est dans `growthos/AUTOEDIT_CONTRACT.md`. La route frontend `/autoedit` gère sélection de fichier, focus (`best`, `player`, `goals`), numéro de joueur, style, durée, upload direct vers Supabase Storage, confirmation du job et polling. Elle consomme `stageLabel`, progress, erreurs structurées et résultats de revue.

Le squelette backend existe dans `growthos-web` pour `autoedit_jobs`, les routes API, le parsing et les vues de polling. La création et la confirmation restent possibles avec `AUTOEDIT_ENABLED=false`; seul le worker doit rester désactivé. Test local attendu : job simulé en `review` avec `quality.flags=["simulated"]` et `manualReview=true`.

À faire : tester Generate avec `ORIGINALITY_CHECK_ENABLED=true`, valider migration/Storage/worker AutoEdit de bout en bout, puis compiler et tester `growthos-web` avant commit. L'audit TikTok est approuvé; cela débloque la future publication et les analytics TikTok sans changer la priorité immédiate AutoEdit.

### Sous-titres de référence (2026-09-21, changements locaux)

L'utilisateur veut les SOUS-TITRES des exemples FacelessReels : un mot à la fois, en majuscules blanches grasses, contour noir, centré dans la vidéo et calé sur la voix. Il ne demandait pas de refaire les scènes/animations ni la galerie de la landing à partir de cette capture rapprochée.

Modifications non commitées/non poussées dans `engine/captions.py` et `tests/test_captions.py` : adaptation du style existant `bold_stroke` (également style par défaut), événements ASS par mot avec les timings existants, `an5` et position au centre, taille proportionnelle à la résolution (base 90 px en 1080x1920), réduction pour les mots longs, contour noir, majuscules Unicode et blanc même dans le hook. Le maintien après un mot est limité à 80 ms et borné par le mot suivant et la fin du cue. En absence de timings mot à mot, repli sur le texte du cue. Les quiz conservent leur placement de narration antérieur pour éviter de recouvrir les cartes centrales ; les autres styles restent inchangés. Pas de nouvelle valeur de style ni de migration SQL.

Validation : 57 tests (`python -m unittest tests.test_captions tests.test_quiz tests.test_script`) réussis. Démonstration silencieuse FFmpeg avec timings d'exemple : `growthos/output/caption-reference/preview.mp4`, capture `preview.jpg`, fichier `preview.ass`. Rendu de la capture inspecté. Ce n'est pas un test complet de génération avec voix réelle. Les vidéos déjà rendues doivent être régénérées pour adopter le nouveau style.

Frontend correspondant également local : aperçu de `bold_stroke` et descriptions FR/EN dans `growthos-web`. Le frontend HEAD poussé est `8981b27`, uniquement la charte de la landing ; les sous-titres ne sont pas déployés. Voir `growthos-web-frontend.md`. Préserver les modifications de mémoire déjà présentes avant cette session.

### Caption commits pushed (2026-09-21, supersedes local-only status above)

User explicitly requested commit + push of the caption changes. Engine commit `ea52cc4` is pushed to `AiAddicts/origin/growthos/mvp`; frontend commit `b0ed949` is pushed to `growthos-web/origin/master`. These contain the centered white uppercase word-by-word captions, tests, UI preview, and FR/EN descriptions. Previous validation: 57 engine tests, 38 frontend tests, TypeScript, targeted ESLint, and production build passed. Deployment/worker rollout was not verified; existing rendered videos require regeneration. Memory files remain local and were excluded from these implementation commits.

### AutoEdit production path and creative rendering (2026-09-25)

AutoEdit is no longer a simulated skeleton. Backend `growthos/mvp` now has a real local FFmpeg pipeline: scene changes and relative audio peaks, deterministic EDL, vertical 720x1280 render with audio, private result storage, poster, review state and bounded retries. The worker is enabled with the signals analyzer (`6ff3233`). Results live in private `autoedit-results`; the web API signs URLs for 2 hours after an RLS-scoped job read. Source and result expire after 7 days by default (`AUTOEDIT_RETENTION_DAYS`), daily purge keeps the job history and marks it purged. Main commits: `1705353`, `ab1f597`, `d342d22`, `6ff3233`.

Audio/profile work is pushed: `6ffaf0d` added Eleven Music for sports rushes with no or quasi-inaudible audio and Scribe word timestamps for the `general` profile; `36e9586` fixed oversized captions and cost tracking. Sports with usable original audio never receives generated music. General sends only the selected edit to Scribe, then burns the existing word-by-word caption style. Provider failures are best-effort and force manual review instead of failing the render. The schema migration `20260925190000_autoedit_general_profile.sql` expands the existing profile constraint from sports-only to `sports | general`; it was committed but could not be applied from this machine because no SQL/linked Supabase CLI credentials were available. Confirm application before relying on General in production.

Creative EDL v2 is pushed in `e12b2e7`: bounded slow motion with matching `atempo`, first-impact freeze frame, Hype punch zoom, at most two short white flashes, and a single progressive zoom for Cinematic/Emotional. FFmpeg executes these fields deterministically; validation rejects unknown/unbounded values. A real synthetic two-clip smoke render produced both video and audio at the expected duration after fixing SAR normalization between zoom types. Validation at delivery: 313 backend tests passed.

Current important limitation: event selection is still signal-based, not semantic. It does not yet prove that a moment is a goal, identify a player, track a face/subject, or understand the key sentence of an interview. The next quality milestone is semantic vision/audio understanding plus dynamic subject tracking, then beat-aware cutting and sound design. Preserve one EDL contract; do not add a parallel job/result shape.

### Motion Graphics sans sous-titres (2026-09-30)

The user wants an optional way to omit spoken-word captions on Motion Graphics videos while keeping narration audio and all text/data inside the animated graphic. Current engine behavior always builds `captions.ass` and `video.render_final` always applies the subtitles filter, regardless of `visual_style`; current caption-style contract has only visual presets and no `none` value. Do not ship a frontend-only option: `engine.script.validate_script` currently rejects unknown caption styles, and the renderer will still burn captions unless Claude adds backend support. Ownership per `AGENTS.md`: Claude Code owns engine/rendering/backend contracts; Codex owns the growthos-web UI. Backend contract proposal: allow an explicit captions-disabled value/flag, skip caption rendering/filter when disabled, keep TTS unchanged, preserve current defaults for all existing content. Keep Motion Graphics safe-area layout in mind: its scenes reserve the current caption zone, so disabling captions could optionally allow a later layout recalculation. User's latest request was “update memory”; no implementation, commit or push for this feature has happened.
