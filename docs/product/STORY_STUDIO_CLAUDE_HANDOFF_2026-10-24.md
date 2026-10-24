# STORY STUDIO — HANDOFF CLAUDE CODE / REPRISE QUALITÉ
Date: 2026-10-24. Owner: Faceloop. Statut: **NO-GO sur le renderer procédural**, reprise orientée références.

## Décision produit non négociable
L'utilisateur a vu le MP4 Néo/Orion du prototype Python/Pillow et l'a rejeté explicitement : « c'est vraiment nul, pas comme les vidéos de références ». Ce rejet annule tout discours de succès fondé uniquement sur la génération d'un MP4, la présence d'un workflow ou des tests unitaires. **Ne pas polir ce prototype pour le présenter comme un dessin animé de qualité.** Ne pas fusionner PR #72 telle quelle.

La promesse est un Story Studio capable de créer des histoires **réellement animées**, avec personnages cohérents, expressions, actions, interactions, décors, cadrages et voix/lip-sync. Les références sont des objectifs qualitatifs, pas des assets à recopier.

## Références essentielles (à obtenir avant toute décision artistique)
Deux fichiers de référence fournis par l'utilisateur dans sa bibliothèque ChatGPT :
- `/Faceloop/Story Studio/References/Te-voila-case_reference.mp4` (environ 2 min, 512x910, 30 fps)
- `/Faceloop/Story Studio/References/C-est-garanti_reference.mp4` (environ 1 min 39, 512x910, 30 fps)
- Contact sheet : `/Faceloop/Story Studio/References/story_video_contact_sheet.jpg`.

**ATTENTION** : ces chemins sont dans la bibliothèque ChatGPT, **pas dans GitHub**. Claude Code ne peut pas présumer les lire. Demander à l'utilisateur de les mettre dans un répertoire local accessible à Claude, ou fournir un lien partagé autorisé. Ne pas les committer dans GitHub sans vérification de licence, consentement et taille. Ne pas inventer une analyse des références sans les visionner. Réaliser ensuite un découpage image par image / plan par plan : identité des personnages, style, timing, mouvements, décors, transitions, expressions, caméra, voix, rythme, montage et qualité.

## Dépôts et état
Backend : `SDAiAutomation/AiAddicts`, base `growthos/mvp`.
Frontend : `SDAiAutomation/growthos-web`.
PR #71, `docs/story-studio-animation-recovery` : https://github.com/SDAiAutomation/AiAddicts/pull/71 — audit, critères, architecture et sécurité.
PR #72, `feat/story-studio-offline-animation-spike` : https://github.com/SDAiAutomation/AiAddicts/pull/72 — expérimentation isolée, **non approuvée artistiquement**.
Dernier commit PR #72 observé : `6581e6801246394af3df3f0217f4a487cc7325dd`.
Les deux PR sont en brouillon, non fusionnées. Ne pas les confondre avec la production.

Fichiers à inspecter :
- Frontend : `src/app/(app)/story-studio/{page.tsx,story-editor.tsx,actions.ts,ai-actions.ts}`, `src/lib/story-studio/{storyboard.ts,render.ts,scenes.ts,proposal.ts}`.
- Backend : `growthos/engine/{story_compile.py,script.py,assembler.py,visuals.py,storage.py,repo.py,tts.py,video.py}`, `growthos/worker.py`, `growthos/engine/story_intelligence/`.
- Spike rejeté : `growthos/engine/story_animation_spike/{timeline.py,render_demo.py,test_timeline.py,test_render_demo.py}`.
- CI : `.github/workflows/story-animation-offline-spike.yml`, workflows Story frontend/backend.
- Documentation : `docs/product/STORY_STUDIO_STEP_01_GENERATION_PATH_2026-10-24.md`, `STEP_02_SECURITY_STORAGE_AUDIT_2026-10-24.md`, `STEP_03_ARCHITECTURE_2026-10-24.md`, `STEP_04_OFFLINE_PROTOTYPE_2026-10-24.md` sur PR #71.

## Architecture actuelle et risques
L'éditeur Story existe et enregistre des scripts ; le compilateur Story produit des blocs illustrés statiques, pas de vraie animation. Le worker, la file, les voix, crédits, versionnement et stockage sont mutualisés. `content-videos` a été créé historiquement public ; `growthos/scripts/activate_private_generate.py` prévoit une activation privée séparée. **État actuel inconnu**, à vérifier en lecture seule. `storage.py` utilise `upsert=true` sur des chemins versionnés. L'E2E Story éditeur→queue→worker→MP4 n'est pas prouvé. Ne pas exposer de données ni déclencher de coût payant sans accord.

## Plan de reprise à respecter
**Phase A — Références et diagnostic** : lire le repo, obtenir les deux MP4, établir une matrice comparative visuelle/animation/son, distinguer animation 2D riggée, vidéo générative et hybridation. Mesurer le fossé, contraintes de coûts, droit d'usage, licences et stabilité de personnage. Documenter un GO/NO-GO des approches avec exemples vérifiables, pas une préférence arbitraire pour Godot.
**Phase B — Prototype de fidélité** : produire **un seul plan de 5–8 secondes** au niveau artistique cible, avec personnage original riggé, expressions, vraie action et caméra ; puis un second personnage et interaction. Commencer avec assets de qualité (créés/licenciés), pas formes Pillow. Le moteur peut être Godot, Blender Grease Pencil, Live2D/Rive ou un service vidéo adapté : décider après tests de qualité/coût/droits.
**Phase C — Voix et synchronisation** : voix stable par personnage, timings mesurés, bouche/visèmes liés au son ; test audio réel seulement après budget et consentement. Pas de lip-sync simulé présenté comme vrai.
**Phase D — Produit** : contrat versionné, adaptation au worker et frontend via feature flag OFF, compatibilité Standard/Quiz, sécurité multi-tenant, crédits atomiques/refunds, stockage privé, cache, quotas, E2E, monitoring, rollback.

## Gates et critères d'acceptation
1. **Gate 0** : accès aux références confirmé, analyse documentée, exemples visuels et critères de style approuvés par l'utilisateur.
2. **Gate 1** : démonstration vidéo courte évaluée **visuellement** par l'utilisateur ; mouvements expressifs, style homogène, personnages reconnaissables d'un plan à l'autre. Un MP4 valide ou un test vert ne suffisent pas.
3. **Gate 2** : dialogue naturel et lip-sync audio vérifié sur lecture vidéo, timing et expressions.
4. **Gate 3** : récit 15–30 s en 9:16, 3+ plans, 2 personnages récurrents, action et réaction, caméra et décors cohérents ; revue qualité de l'utilisateur.
5. **Gate 4** : E2E produit sécurisé, crédits, multi-tenant, coût mesuré, régressions Standard/Quiz et pilote opt-in.
À chaque gate : rapport preuves/vidéo, coût, limites, décision GO/NO-GO ; ne pas avancer si gate échoue.

## Exigences de gestion de projet
- Conserver le travail existant, ne pas effacer PR #71/#72 ; marquer clairement l'ancien renderer comme expérimentation rejetée.
- Faire de petites PRs, commits cohérents, fichiers de documentation et tests. Jamais de commit de secrets, références tierces ou vidéos volumineuses sans accord.
- Produire une seule source de vérité `docs/product/STORY_STUDIO_MASTER_PLAN.md` dans une nouvelle branche, tableau phases, tâches, propriétaires, dépendances, risques, preuves, coûts et état.
- Aucune modification de production, aucune API payante, aucun déploiement sans validation explicite.
- Signaler ce qui est réellement exécuté vs seulement écrit ; vérifier CI au lieu de le supposer.
- Si les références ne sont pas accessibles, s'arrêter à Gate 0 et demander exactement comment les recevoir ; ne pas remplacer leur analyse par des suppositions.
