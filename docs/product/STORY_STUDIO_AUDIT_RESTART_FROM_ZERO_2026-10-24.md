# Story Studio — audit de reprise à zéro (24 octobre 2026)

## Sens de « recommencer à zéro »
**Repartir de zéro dans l'évaluation et la conception, pas effacer le code ni les données.** L'existant est gelé pour étude. Aucune suppression, reset Git, réécriture de branche, migration DB, désactivation en production ni modification du code. Décider après inventaire ce qui est conservé, refactoré, remplacé ou abandonné.

## Périmètre effectivement vérifié (lecture seule)
Dépôt frontend `SDAiAutomation/growthos-web` (ref par défaut au moment de la lecture) :
- `src/app/(app)/story-studio/page.tsx` : route fonctionnelle, contrôle d'organisation et droits, lecture de projets depuis Supabase, restriction admin + flag de génération.
- `src/app/(app)/story-studio/story-editor.tsx` : éditeur client substantiel (~32k caractères), personnages Néo/Orion préremplis, voix, scènes, étapes, proposition IA, sauvegarde et action de mise en file.
- `src/app/(app)/story-studio/actions.ts` : sauvegarde dans `content_items`, format `story`, RLS côté client, contrôles d'édition ; action de génération annoncée comme payante, déclenchement de worker et protections à approfondir.
- `src/app/(app)/story-studio/ai-actions.ts` : propositions de plan et scènes via OpenAI, quota IA, modèle configurable ; prompt de type `illustrated dialogue story`, non plan d'animation.
- `src/lib/story-studio/storyboard.ts` : validations, parsing, persistance, IDs, édition ; `Shot` = id/speaker_id/dialogue/duration_s ; limite 30 plans pour l'éditeur.
- `src/lib/story-studio/render.ts` : garde-fous de mise en file, estimation images et voix, limite de 12 plans et 3 tentatives ; feature flag.
- `docs/product/STORY_STUDIO_VISION.md` : vision explicitement non implémentée ; recommande de conserver l'entrée Create video / Standard / Quiz / Story et la distinction Story Studio / Story Intelligence.

Dépôt backend `SDAiAutomation/AiAddicts`, branche `growthos/mvp` :
- `growthos/engine/story_compile.py` : conversion de Story vers blocs texte/voix/image illustrée ; limite 12 plans ; pas de contrat animé. Son commentaire sur l'absence de branchement est obsolète.
- `growthos/engine/script.py` : `normalize_script` appelle effectivement `story_compile.compile_story(quiz.compile_quiz(data))`.
- `growthos/engine/story_intelligence/validator.py` : validateur déterministe IDs, voix via speaker_id, dialogue, durée ; pas d'action/rig/caméra.
- `growthos/engine/story_intelligence/timing.py` : réalignement hors ligne sur durées audio fournies ; ne mesure pas lui-même l'audio.

## Ce qui existe déjà et qu'il ne faut pas jeter aveuglément
- Route et éditeur Story Studio.
- Sauvegarde et reprise de brouillons, structure de personnages, voix et scènes.
- Propositions IA, quotas, autorisations et contrôles de mise en file.
- Validations Python et TypeScript, logique de timing, branchement au contrat de blocs historique.
- Documentation de vision et premiers pilotes.

## Limites de l'existant
- L'éditeur et les données sont orientés dialogue illustré, pas animation corporelle.
- Aucune preuve de rendu animé 2D réel ni de MP4 conforme aux références n'a été observée dans les fichiers vérifiés.
- Incohérence entre 30 scènes éditables et 12 rendables.
- Les commentaires sur le branchement Story ne reflètent pas toujours le code.
- La sécurité complète des workers, coûts, tests, stockage, droits, et intégrations reste à auditer avant conclusions.

## Décision provisoire : reconstruire la capacité, pas le produit entier
**Conserver sous réserve d'audit** : infrastructure auth/RLS, projets, voix, UI existante, quotas, observabilité, outils de rendu génériques.
**Refondre probablement** : modèle de scène, Story Intelligence et prompts, contrat d'animation, moteur de rendu Story, prévisualisation.
**Ne pas décider encore** : suppression de code ancien, changement de moteur, migrations DB, architecture worker, réutilisation précise de composants.
**Protéger** : Standard, Quiz, utilisateurs et projets existants.

## Inventaire encore nécessaire avant « audit complet »
1. Lire entièrement `actions.ts`, `ai-actions.ts`, `story-editor.tsx`, `scenes.ts`, `proposal.ts`, `worker-trigger.ts`, modules de crédit/permissions.
2. Trouver les entrypoints workers, dispatch des formats, synthèse vocale, images, assemblage FFmpeg, upload et état des jobs.
3. Lister les tests et fixtures frontend/backend, exécuter hors production quand possible.
4. Vérifier migrations Supabase, RLS et isolation tenant ; budget, retries, erreurs et idempotence.
5. Revoir toutes les branches/PRs Story et comparer à la base actuelle ; la recherche de code GitHub via connecteur n'a retourné aucun résultat, donc ne pas prétendre à un inventaire exhaustif.
6. Benchmark indépendant Godot/Blender/Rive, puis décision GO/NO-GO.

## Ordre de redémarrage
G0 photographie vérifiée de l'existant ; G1 inventaire complet ; G2 matrice garder/refondre/retirer ; G3 benchmark et prototype 2D isolé ; G4 contrats ; G5 intégration sous feature flag ; G6 E2E et sécurité ; G7 décision de lancement.

**Aucun code supprimé ou réinitialisé.** Les décisions de refonte et les modifications du code requièrent validation spécifique après l'audit.
