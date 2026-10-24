# Story Studio — Master Plan (source de vérité)
Date : 2026-10-24. État : **Gate 0 livré pour validation utilisateur** (2026-10-24, rapports `STORY_STUDIO_GATE0_*`). Aucun nouveau renderer n'est écrit ; Gate 1 attend l'approbation explicite.

## Vision et résultat
Faceloop Story Studio doit produire des courts métrages 2D animés, publiables et cohérents, pas un diaporama d'images ni des figures géométriques animées. La qualité artistique est un critère de livraison bloquant. Priorité : qualité et réutilisation des assets, puis coût, puis intégration.

## État réel
- PR #71 : documentation/audit ; à conserver.
- PR #72 : code expérimental offline (timeline, Pillow, tests, CI) ; renderer NO-GO artistique, ne pas fusionner.
- Backend existant : worker, credits, TTS, stockage, compilateur de plans illustrés.
- Frontend existant : Story Studio, éditeur, propositions IA, persistance et queue.
- Tests CI et E2E : CI de la PR #72 **rouge** (ffmpeg absent du runner) ; E2E Story jamais exécuté ; tests `story_intelligence` non exécutés en Gate 0.
- Bucket `content-videos` : **privé** (vérifié en lecture seule le 2026-10-24) ; immutabilité `upsert=true` non prouvée.
- Références utilisateur : reçues et **analysées** (zip de transfert) ; conservées hors dépôt (public, contenu tiers).

## Tableau des phases
| Phase | Livrable | Dépendances | Preuve requise | Gate |
| --- | --- | --- | --- | --- |
| A0 | Références accessibles, droit d'usage clarifié, inventaire code | MP4 utilisateur | fichiers lisibles + métadonnées | 0 — **fait** |
| A1 | Analyse plan par plan, matrice de qualité, options techniques | A0 | captures annotées + scorecard | 0 — **fait** (planches locales + `GATE0_REFERENCE_ANALYSIS`) |
| A2 | Choix moteur et budget comparés | A1 | benchmarks reproduisibles et licences | 0 — **comparatif fait, benchmarks reportés à Gate 1 (bake-off R vs G)** ; en attente d'approbation |
| B1 | Personnage original et rig/asset bible | A2 | model sheet + poses/expressions | 1 |
| B2 | Plan animé 5–8 s | B1 | vidéo regardable, vraie action/caméra | 1 |
| C1 | Deux personnages + dialogue + visèmes audio | B2 | comparaison bouche/voix à la lecture | 2 |
| C2 | Histoire 15–30 s, 3+ plans, 9:16 | C1 | vidéo complète validée visuellement | 3 |
| D1 | Contrat versionné, adapter et flag OFF | C2 | tests contractuels + legacy OK | 4 |
| D2 | UI, worker, credits, cache, stockage, E2E | D1 | preuve E2E et coût mesuré | 4 |
| D3 | Pilote limité + rollback | D2 | autorisation utilisateur explicite | 4 |

## Critères mesurables de qualité (à affiner avec les références)
- Cohérence : même identité, palette et proportions des personnages entre plans.
- Animation : gestes intentionnels et transitions de poses ; aucune oscillation générique en guise d'action.
- Visage : émotions lisibles, regard dirigé, clignements contextuels.
- Dialogue : voix distinctes et stables ; lèvres synchronisées au son mesuré, pas au simple temps.
- Cinéma : au moins trois cadrages utiles, changements de plans motivés, profondeur et décors continus.
- Export : 9:16, lecture mobile fluide, texte lisible, audio intelligible.
- Coût : présenter coût variable/vidéo, coût fixe/asset, temps de rendu et risques de dépendance.
La validation humaine sur lecture de la vidéo est obligatoire, en plus des métriques et tests.

## Risques prioritaires et atténuation
1. **Qualité insuffisante** : Gate 1 bloque toute intégration, comparer réellement aux références.
2. **Inaccessibilité des références** : demander les fichiers, ne pas inventer une analyse.
3. **Mauvaise technologie** : benchmark comparatif avant investissement dans un moteur.
4. **Dérive des coûts** : spike offline, quotas, cache, aucun appel payant non approuvé.
5. **Sécurité médias** : vérifier état réel `content-videos` et accès signé.
6. **Multi-tenant** : tester isolation sous service_role et côté web.
7. **Régressions** : feature flag OFF, ne pas toucher Standard/Quiz avant tests.
8. **Droits et propriété intellectuelle** : assets originaux/licenciés, ne pas copier références.
9. **Validation trompeuse** : distinguer code commité, CI réellement passée et rendu évalué.

## Règles de gouvernance
Responsable produit/approbation : utilisateur. Responsable exécution : Claude Code. Claude doit documenter chaque décision et fournir la preuve visuelle avant de réclamer un GO. Pas de merge ni de déploiement automatique. Commits et PRs petites et explicites ; secrets et vidéos de tiers exclus. Maintenir ce document à jour à chaque gate, avec statut, liens, coûts, tests et décisions.

## Premier ticket pour Claude
Lire `STORY_STUDIO_CLAUDE_HANDOFF_2026-10-24.md` et ce plan. Vérifier les deux dépôts et PRs. Obtenir accès aux deux MP4, réaliser Gate 0 (analyse, comparaison et sélection de technologie justifiée). **Ne pas écrire un nouveau renderer avant la fin de Gate 0.**

## Journal des gates
- **Gate 0 (2026-10-24)** : analyse des références, écart avec le prototype rejeté, audit du code, comparatif, architecture, feuille de route : voir `STORY_STUDIO_GATE0_REFERENCE_ANALYSIS_2026-10-24.md` et `STORY_STUDIO_GATE0_ENGINE_AND_ARCHITECTURE_2026-10-24.md`. Décision : **GO conditionnel au bake-off Gate 1** ; **NO-GO** sur le rendu procédural Pillow et sur toute intégration produit avant Gate 3. Coût engagé : 0 $.
- **Gates 1 à 3c (2026-10-24)** : prototype de marionnette 2D (Godot) avec art généré par l'API OpenAI de Faceloop, deux personnages, voix ElevenLabs, sous-titres, musique synthétisée, 1080×1920 ; clip Gate 3c jugé « assez bon » par l'utilisateur. Rapport : `STORY_STUDIO_GATE1_REPORT_2026-10-24.md` (PR #74). Coûts mesurés/estimés : ≈ 0,24 USD d'images, 393 caractères ElevenLabs.
- **Gate 4 (2026-10-24, plan seulement)** : `STORY_STUDIO_GATE4_INTEGRATION_PLAN_2026-10-24.md` — contrat `animation_schema_version: 1`, flag OFF, aiguillage du worker avant la réservation du crédit, remboursements, quotas, tests, 7 PR de code à ouvrir après accord. **Rien n'est implémenté.**
