# Script Engine : planification en deux étapes (2026-10-11)

Expérience locale (branche non poussée `experiment/script-two-step-20261011` du dépôt web, variable `SCRIPT_TWO_STEP=1`). Un Planificateur (1 appel, `gpt-5-mini`, `reasoning_effort: low`) produit promesse, indices, révélation, fin et un beat par bloc avec son budget de mots ; le Rédacteur existant écrit ensuite la narration avec ce plan ajouté à la demande, avec la même validation et la même relance. Banc identique aux précédents : 10 sujets × 6 répétitions = 60 générations par série, `master` après #57/#58/#61 ; base = `reasoning_effort: low` actuel.

## Fiabilité

| | Base | Deux étapes |
|---|---|---|
| Réussite à la 1re rédaction | 1/60 = 2 % [0-9] | 26/60 = 43 % [32-56] |
| Réussite définitive | 46/60 = 77 % [65-86] | 53/60 = 88 % [78-94] |
| Appels moyens (planificateur inclus) | 1,98 | 2,57 |
| Mots du 1er essai, médiane | 149 | 218 |
| 1er essai sous 206 mots | 59/60 | 20/60 |
| Mots par bloc point | 17,3 | 20,2 |
| Blocs moyens (finals) | 10,8 | 11,8 |
| Coût estimé par script réussi | 0,0128 $ | 0,0152 $ (+19 %) |
| Durée moyenne | 22 s | 32 s |
| Rejets longueur / plans / hook | 71 / 3 / 0 | 25 / 12 / 9 |
| Blocs-étiquette par script | 0,28 | 0,04 |

La première rédaction passe presque toujours en base **trop courte** (59/60) ; avec un plan chiffré par bloc, elle est dans les bornes 40 % du temps. Le gain définitif (77 → 88 %) n'est pas établi (intervalles qui se chevauchent). Les rejets restants viennent des plans identiques et des hooks trop longs, que les réparations déterministes de la PR #60 traitent.

## Qualité (juge LLM en aveugle, ordre inversé, 41 paires ; même famille que le générateur)

| Critère | Deux étapes | Base |
|---|---|---|
| hook | 11 | **42** |
| cohérence | 11 | **34** |
| révélation préparée | 20 | 27 |
| originalité | 27 | 27 |
| plausibilité | 12 | 21 |
| facilité visuelle | 15 | **30** |
| conclusion | 22 | 33 |
| moins de remplissage | 14 | **41** |
| moins de répétition | 15 | **39** |
| narration naturelle | 12 | **43** |
| scènes utiles | 13 | **34** |
| dénouement mérité | 15 | **32** |
| global | 15 | **40** |

Sur 29 paires jugées de façon constante dans les deux ordres, 16 favorisent la base, 4 les deux étapes. Relecture : en deux étapes, la narration devient une **description de caméra** (« Plan rapproché sur le balcon… », « Séquence montrant plusieurs matins », « Le plan révèle la boîte ») : le champ `what` du plan, formulé comme « ce qu'on voit », a fui dans la voix off. L'histoire du corbeau perd son sens (aucune révélation) ; celle des frères reste lisible mais plus plate.

## Décision

**NO-GO pour cette implémentation.** Le plan règle le problème mécanique (longueur au premier essai, étiquettes) mais dégrade nettement hook, naturel de la narration et cohérence, pour +19 % de coût et +45 % de durée.

## Piste si on la rouvre
Le gain de longueur vient du budget de mots par bloc, pas de la description du contenu. À tester : un plan qui donne seulement les événements (faits, pas cadrage), formulés de façon neutre, sans « ce qu'on voit », avec les mêmes budgets ; les réparations de la PR #60 pour plans et hook ; et un contrôle des mots de caméra (« plan », « gros plan », « séquence ») dans la narration.

## Limites
60 générations par série ; un modèle, un profil, une langue ; juge LLM de la même famille ; coût estimé (échecs au prix d'un succès) ; relecture humaine limitée à deux exemples lus par l'auteur de l'expérience.
