# Benchmark de bout en bout (lot L5)

Mesure ce que coûte et ce que vaut réellement une vidéo Faceloop, du brief à la vidéo rendue. Complète `content/scripts/retention/BENCHMARK.md`, qui est une analyse déterministe sans rendu ni dépense.

**Rien de ce document n'a été exécuté.** Aucun résultat n'est publié ici : les seuils ci-dessous sont des hypothèses à confirmer ou corriger après un premier passage.

## Budget

Mesure existante : environ 0,34 à 0,37 $ par vidéo complète (audit du 2026-10-03). Un retouche où presque tout est réutilisé coûte beaucoup moins (0,0156 $ relevé sur une vidéo de 5,7 s).

| Brief | Coût attendu |
|---|---|
| 30 briefs, une génération chacun | environ 10 à 11 $ |
| + 5 retouches (étape 4) | environ 1 $ |
| Plafond à ne pas dépasser sans nouvel accord | 15 $ |

Arrêter si le coût moyen des 5 premières vidéos dépasse 0,60 $.

## Préparation

1. Créer un compte dédié « Benchmark » (ou réutiliser un compte interne) sur l'espace « GrowthOS Dogfooding », marqué `is_internal = true`. Les événements ne polluent alors pas les chiffres clients.
2. Aucune publication : laisser la publication en « Manuel » et ne publier aucune vidéo du benchmark.
3. Créer chaque vidéo dans l'application avec le titre `[BENCH-nn] <brief>` (le repère permet de les retrouver). Respecter la langue et le style de `briefs.json`.

## Passage

1. **Génération.** Lancer les 30 vidéos, par lots de 5 à 10 pour ne pas saturer le worker. Noter l'heure de mise en file.
2. **Contrôle automatique.** Exécuter `report.sql` (éditeur SQL) : réussite, statut, coût, durée, drapeaux qualité.
3. **Contrôle humain.** Regarder 10 vidéos tirées au sort (au moins 2 par format) et noter chacune de 1 à 5 : accroche, voix, sous-titres, cohérence visuelle, fidélité au brief. Cliquer « Je suis satisfait » sur celles qui le méritent : le coût par vidéo satisfaisante se calcule ensuite.
4. **Correction.** Sur 5 vidéos, corriger une phrase puis relancer. Vérifier dans l'encart « Ce qui sera refait » que seule une voix est annoncée, puis comparer le coût du second run à celui du premier.

## Critères (hypothèses de départ)

| Mesure | Cible |
|---|---|
| Vidéos qui atteignent le statut `video` | au moins 27 sur 30 (90 %) |
| Statut `quality_check` | au plus 20 % |
| Coût médian par vidéo | au plus 0,40 $ |
| Coût P90 | au plus 0,60 $ |
| Délai médian de mise en file à vidéo | au plus 20 min |
| Second run d'une correction | au plus 20 % du coût du premier |
| Note humaine moyenne (10 vidéos) | au moins 3,5 sur 5 |

Les briefs 27 à 30 sont volontairement difficiles (brief d'un mot, noms propres, sujet trop large, contrainte sans personnage). Un échec propre y est acceptable ; un échec silencieux ou une vidéo hors sujet ne l'est pas.

## Ce que ce benchmark ne mesure pas

- La performance des vidéos auprès d'un public : aucune n'est publiée.
- La qualité des quiz, qui ont un autre flux de création.
- Le coût du stockage et du transfert, toujours inconnu.
