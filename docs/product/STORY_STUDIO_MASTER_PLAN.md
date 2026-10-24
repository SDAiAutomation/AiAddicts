# Story Studio — Master Plan (source de vérité)
Date : 2026-10-24. État : Gate 0 bloqué tant que les références ne sont pas accessibles dans l'environnement Claude.

## Vision et résultat
Faceloop Story Studio doit produire des courts métrages 2D animés, publiables et cohérents, pas un diaporama d'images ni des figures géométriques animées. La qualité artistique est un critère de livraison bloquant. Priorité : qualité et réutilisation des assets, puis coût, puis intégration.

## État réel
- PR #71 : documentation/audit ; à conserver.
- PR #72 : code expérimental offline (timeline, Pillow, tests, CI) ; renderer NO-GO artistique, ne pas fusionner.
- Backend existant : worker, credits, TTS, stockage, compilateur de plans illustrés.
- Frontend existant : Story Studio, éditeur, propositions IA, persistance et queue.
- Tests CI et E2E : non confirmés.
- Références utilisateur : deux MP4 dans bibliothèque ChatGPT, non présents dans les dépôts.

## Tableau des phases
| Phase | Livrable | Dépendances | Preuve requise | Gate |
| --- | --- | --- | --- | --- |
| A0 | Références accessibles, droit d'usage clarifié, inventaire code | MP4 utilisateur | fichiers lisibles + métadonnées | 0 |
| A1 | Analyse plan par plan, matrice de qualité, options techniques | A0 | captures annotées + scorecard | 0 |
| A2 | Choix moteur et budget comparés | A1 | benchmarks reproduisibles et licences | 0 |
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
