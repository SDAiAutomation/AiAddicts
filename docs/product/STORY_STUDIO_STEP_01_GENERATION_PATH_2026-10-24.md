# Story Studio — étape 1 : chemin réel de génération et décisions de conservation

Date : 2026-10-24. Analyse de code **en lecture seule**, sans tests, exécution de worker ni dépenses.

## Chaîne observée
1. `growthos-web/src/app/(app)/story-studio/actions.ts` : `saveStoryProject` écrit le JSON `script.story` dans `content_items`, statut `idea`. `queueStoryGeneration` exige feature flag, admin, rôle, confirmation de coût, statut admissible, nombre de tentatives, validation, modération et crédits ; met le projet en file.
2. `growthos-web/src/lib/worker-trigger.ts` : dispatch facultatif du workflow GitHub Actions `growthos-worker.yml` sur `growthos/mvp`; cron en secours, non garanti à la minute.
3. `AiAddicts/growthos/worker.py` : `process_one` réclame un item avec `repo.claim_queued_item` et appelle `assembler.run_for_content_item(content_item_id)`. Worker partagé avec trim, export Quiz et AutoEdit.
4. `AiAddicts/growthos/engine/repo.py` : claim conditionnel des jobs ; récupération de jobs abandonnés ; `reserve_generation_credit` et `refund_generation_credit` passent par des RPC Supabase.
5. `AiAddicts/growthos/engine/assembler.py` : voix par bloc seulement pour `content_format == story` ; `run_for_content_item` réserve le crédit avant génération et rembourse sur échec. Le reste du pipeline gère audio, visuels, rendu et upload génériques.
6. `AiAddicts/growthos/engine/script.py` : compilation Story en blocs illustrés via `story_compile`.

## Décisions, étape 1
- **GARDER** : sauvegarde des brouillons, authentification/autorisation, queue conditionnelle, dispatch, worker partagé, RPC crédits, voix par bloc, traitement audio, stockage et outils FFmpeg (sous réserve de tests).
- **ISOLER** : un futur moteur d'animation derrière une interface explicite `StoryAnimationRenderer`, sans remplacer le pipeline Standard/Quiz.
- **REFONDRE** : ShotPlan versionné, actions/émotions/caméra, assets de personnages, lip-sync et contrôle de continuité.
- **NE PAS FAIRE** : effacer les projets, migrer le schéma Supabase immédiatement, déclencher `workflow_dispatch`, activer le flag de génération sur Production, tester sur le projet Supabase partagé, engager des API payantes.

## Risques immédiats
- L'E2E Story actuel n'est pas prouvé : `growthos-web/docs/product/STORY_STUDIO_FIRST_RENDER.md` le dit explicitement.
- Le worker partage la file avec d'autres formats ; un essai mal isolé pourrait traiter de vrais jobs.
- Un rendu Story historique et un rendu animé ne doivent pas être confondus : conserver le premier sous version distincte.
- Les tests de garde-fous présents sont utiles mais ne prouvent pas une animation réussie.

## Prochaine étape séquentielle
**Étape 2 : audit détaillé de l'assembleur, du stockage, des migrations RLS et des tests CI historiques**, puis matrice de compatibilité et proposition d'un spike offline. Aucun code de production ne change avant la décision de migration.
