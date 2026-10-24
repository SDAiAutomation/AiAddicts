# Story Studio — audit structurel étendu et stratégie de reconstruction

Date : 2026-10-24. **Lecture seule** de GitHub, sans tests exécutés ni appels API payants. Cette note complète `STORY_STUDIO_AUDIT_RESTART_FROM_ZERO_2026-10-24.md` et ne prétend pas à une validation E2E.

## Inventaire des dépôts
Inventaire via arbres GitHub récursifs : AiAddicts `growthos/mvp` : 584 entrées, `truncated=false` ; growthos-web branche par défaut : 647 entrées, `truncated=false`. L'inventaire des chemins est complet pour ces refs à cet instant, **mais pas la revue du contenu de chaque fichier**.

### Frontend existant
- `src/app/(app)/story-studio/{page.tsx,story-editor.tsx,actions.ts,ai-actions.ts}`
- `src/components/story-studio/character-voice-picker.tsx`
- `src/lib/story-studio/{storyboard.ts,render.ts,scenes.ts,proposal.ts}`
- `src/lib/worker-trigger.ts` : workflow_dispatch GitHub Actions vers `growthos-worker.yml`, par défaut branche `growthos/mvp`, cron en repli ; le dispatch est best-effort.
- Tests : `scripts/story-generate-gate.test.mjs`, `story-proposal.test.mjs`, `story-scenes.test.mjs`, `story-storyboard.test.mjs`, fixture `scripts/fixtures/story-validator-contract.json`, workflow `.github/workflows/story-studio-checks.yml`.
- `docs/product/STORY_STUDIO_FIRST_RENDER.md` : **indique explicitement que l'E2E éditeur → queue → worker → vidéo n'a jamais été exécuté**. Test prévu avec ElevenLabs + images OpenAI payants, flag `STORY_GENERATION_ENABLED=1` réservé aux admins. Le guide mentionne que Preview et Production partagent le même Supabase au moment de sa rédaction ; vérifier avant toute manipulation.

### Backend existant
- `growthos/worker.py` : réclame des `content_items` queued, appelle le pipeline et met à jour les états ; cohabite avec trim, quiz export et AutoEdit.
- `growthos/engine/{assembler.py,video.py,tts.py,storage.py,generation_cache.py,render_preflight.py,story_compile.py}`.
- `growthos/engine/story_intelligence/{validator.py,timing.py,audio_adapter.py,voice_catalog.py,voice_pilot.py}`.
- Tests Story Intelligence : `test_audio_adapter.py`, `test_real_audio_integration.py`, `test_story_compile.py`, `test_timing.py`, `test_validator.py`, `test_validator_contract.py`, `test_voice_catalog.py`, `test_voice_pilot.py`.
- CI : `.github/workflows/story-intelligence-tests.yml` exécute des tests offline sans secrets ElevenLabs.
- Migrations existantes : `20260904090000_content_item_job_queue.sql`, `20260904110000_content_videos_bucket.sql`, `20260915120000_atomic_credit_reservation.sql`, `20261003140000_content_assets.sql`, `20261003180000_content_versions.sql`, ainsi que les migrations de RLS, coûts et crédits.
- Autres moteurs existants à examiner pour réutilisation : `growthos/engine/motion_graphics/renderer.py`, `growthos/engine/explainer/render.py`, `growthos/engine/assembler.py`. Ne pas les assimiler à un moteur de personnages riggés sans inspection.

## Risques et observations vérifiées
1. `STORY_STUDIO_FIRST_RENDER.md` décrit un rendu de scènes illustrées, pas des animations de personnages ; le guide déclare l'E2E non exécuté.
2. `story-generate-gate.test.mjs` contient des tests de verrouillage, d'estimation et de non-contournement de la queue, mais ces tests ne prouvent pas la qualité du MP4.
3. `worker-trigger.ts` peut déclencher un workflow de production : **ne pas l'utiliser comme banc d'essai sans isolation explicite**.
4. `story_intelligence/audio_adapter.py` mesure des fichiers audio existants sans TTS payant, réutilisable.
5. Le pipeline générique Standard/Quiz partage les workers : nécessité d'un adaptateur Story séparé et de tests de régression.
6. Les limites 30 plans éditables / 12 plans rendables et le modèle illustré sont à corriger dans la refonte, mais sans modification prématurée.

## Matrice provisoire de reprise
| Conserver et tester | Étendre/refondre | Ne pas toucher avant vérification |
|---|---|---|
| Auth, Supabase RLS, crédits, stockage, queue | Contrat ShotPlan, rigs, actions, lip-sync, rendu 2D, preview | Migrations DB, secrets, workflow de prod |
| Voix, audio_adapter, FFmpeg, tests existants | Story Intelligence, prompts, contrôle de continuité | Standard, Quiz, AutoEdit |
| UI Story Studio, sauvegarde, catalogue voix | UI de réalisation et régénération ciblée | Données utilisateur et anciens projets |

## Travaux restant avant implémentation
1. Lire les branches conditionnelles exactes de `worker.py`, `assembler.py`, `repo.py`, `storage.py`, `tts.py` et `actions.ts`.
2. Inspecter toutes les migrations et politiques RLS pertinentes, sans exécuter de SQL.
3. Étudier les PR Story historiques et la compatibilité des schémas.
4. Relever les tests CI réellement passés et les limites des tests (les fichiers seuls ne prouvent pas une exécution verte).
5. Construire un benchmark **isolé et gratuit** Godot/Blender/Rive ; valider licences et contraintes headless.
6. Faire approuver l'architecture et le périmètre de refonte avant toute modification de production.

## Conclusion
**Recommencer à zéro = réévaluer la conception et remplacer la capacité illustrée par une capacité animée, pas détruire les fondations existantes.** Aucun effacement, déploiement, modification de code ni dépense n'a été effectué lors de cet audit.
