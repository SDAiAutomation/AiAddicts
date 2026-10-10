# Script Engine : longueur à la première tentative (2026-10-10)

Mission : comprendre pourquoi la première génération est presque toujours sous le minimum dur, et tester deux variantes de prompt. Aucun seuil de durée modifié. Banc hors dépôt (`C:\bo\h58`), code expérimental sur la branche locale `experiment/script-first-pass-length-20261010` du dépôt web (variable `SCRIPT_PROMPT_VARIANT`, non poussée, aucune PR).

## 1. Diagnostic

Profil standard TikTok, français : cible 220-263 mots, minimum dur 206, 7 à 14 blocs, `reasoning_effort: low`, `gpt-5-mini`.

Mesure de la première tentative sur 60 générations (prompt actuel) : médiane 152-157 mots, 59/60 sous 206, 10 blocs (9-14), **17,5 mots par bloc « point »**, hook 8,4 mots, CTA présent 56/60. Soit environ 8,4 + 8 × 17,5 + 10 = 158 mots.

Contradictions et biais dans le prompt actuel :
1. **Nombre de blocs** : « une liste de 8 à 11 blocs » (format) contre « le nombre de blocs vient de l'idée… une idée simple peut tenir en 3 blocs, sans jamais ajouter un bloc pour atteindre un nombre » (rétention) et « point : autant que nécessaire » (structure). Le validateur exige 7 blocs minimum.
2. **Longueur contre concision** : « Densité : le script s'arrête quand l'idée est complète… pas de remplissage pour atteindre une durée », « resserre le contexte et les répétitions », « une idée claire par phrase, coupe les phrases… » tirent vers le bas ; seule la ligne « durée cible 220 à 263 mots » tire vers le haut.
3. **Arithmétique non dite** : 15-28 mots par bloc × 8-11 blocs permet de 112 à 274 mots. Atteindre 220 impose environ 24 mots par bloc à 10 blocs, soit le haut de la fourchette ; le modèle se place en bas (17,5).
4. **Aucun budget par phase** et aucun « compte » demandé, avec un raisonnement réglé sur `low`.
5. Profils : `short` (cible 89-160 mots, 3-12 blocs, « moins de blocs forts valent mieux ») n'a pas ce problème ; `youtube` (213-426 mots, 8-18 blocs) n'a pas été mesuré.

## 2. Variantes (mêmes sujets, modèle, paramètres, retries ; 10 sujets × 6 répétitions = 60 par variante)

- **A** : prompt actuel.
- **B** : « 11 à 12 blocs » (cohérent avec la cible), « environ 10 blocs point », 18-28 mots par bloc (22 en moyenne), objectif explicite 220-263 mots (jamais moins de 206), phrase sur le nombre de blocs réconciliée.
- **C** : mêmes nombre de blocs et phrase réconciliée, plus un budget indicatif de mots par phase (hook ≤10, preuve ≈50 sur 2 blocs, escalade ≈105 sur 5, résolution ≈65 sur 3, cta ≤12), sans total ni moyenne par bloc.

## 3. Fiabilité (intervalles de Wilson 95 %, médianes en bootstrap)

| | A | B | C |
|---|---|---|---|
| Réussite 1re tentative | 1/60 = 2 % [0-9] | 6/60 = 10 % [5-20] | 9/60 = 15 % [8-26] |
| Réussite définitive | 42/60 = 70 % [57-80] | 47/60 = 78 % [66-87] | 54/60 = 90 % [80-95] |
| Appels IA moyens | 1,98 | 1,90 | 1,85 |
| Mots 1er essai, médiane | 157 [151-161] | 188 [182-193] | 186 [176-188] |
| 1er essai sous 206 mots | 59/60 | 50/60 | 51/60 |
| Blocs 1er essai (hors [7,14]) | 10 (0) | 11 (0) | 11 (0) |
| Mots par bloc point | 17,5 | 17,7 | 17,2 |
| Mots finals (réussis), médiane | 230 | 230 | 234 |
| Finals au-dessus de 263 | 4 | 1 | 7 (max 283) |
| Coût estimé par script réussi | 0,0142 $ | 0,0125 $ | 0,0107 $ |

Constat central : **la longueur par bloc ne bouge dans aucune variante** (17,2-17,7 mots, malgré « 22 en moyenne »). Les variantes ne gagnent que par le nombre de blocs (10 → 11) ; la première tentative reste sous 206 mots 83-98 % du temps. Le coût par succès suppose qu'un échec coûte autant qu'un succès à 2 appels (estimation, tarifs `gpt-5-mini`).

## 4. Qualité (juge LLM en aveugle, ordre inversé, 32 paires B contre A, 39 paires C contre A ; un juge de la même famille que le générateur, verdicts non indépendants)

| Critère | B / A | C / A |
|---|---|---|
| hook | 25 / 29 | 31 / 36 |
| cohérence | 21 / 19 | 28 / 33 |
| révélation préparée | **34 / 20** | 28 / 41 |
| originalité | 32 / 25 | 33 / 36 |
| facilité visuelle | 29 / 27 | 27 / 41 |
| conclusion | **37 / 20** | 38 / 33 |
| moins de remplissage | 29 / 35 | **29 / 49** |
| moins de répétition | 30 / 32 | 31 / 44 |
| narration naturelle | 30 / 33 | 36 / 42 |
| scènes utiles | 21 / 27 | **20 / 43** |
| dénouement mérité | **33 / 19** | 31 / 35 |
| global | 35 / 29 | **34 / 44** |

Contrôles déterministes (scripts réussis) : trigrammes répétés 0,7 % / 0,4 % / 0,8 % ; blocs-étiquette (« Conséquence, … », « Résultat, … ») : 0,43 / 0,57 / 0,67 par script, concentrés en finance (1,08 / 1,85 / 1,69 par script de finance, déjà présents dans A).

Relecture (échantillon dans `review.md` du banc) : en C, l'histoire du chien passe de 208 à 283 mots avec des scènes ajoutées (un bénévole qui « pose des questions », un foulard rouge) et celle de la tirelire devient confuse (la vendeuse ferme la vitrine, le vieil homme « explique » en rentrant). La version A de la tirelire est plus resserrée et cohérente. C dépasse la cible dans 7 cas sur 54.

## 5. Décision

- **C : NO-GO.** Meilleure fiabilité (90 %), mais remplissage et scènes inutiles nettement plus fréquents (29 contre 49 et 20 contre 43 sur 78 verdicts), score global défavorable, scripts au-dessus de la cible.
- **B : non concluant, pas de PR.** Qualité globalement équivalente (meilleures révélations et conclusions, un peu plus de remplissage), fiabilité qui monte de 70 à 78 % et de 2 à 10 % à la première tentative, mais les intervalles se chevauchent et le niveau reste très loin de l'objectif de 5 % d'échecs.
- Aucune variante ne justifie un changement du prompt de production sur ces preuves.

## 6. Hors périmètre mais important

- **Bug d'élision (production)** : `fixFrenchElisions` utilise `\b` sans drapeau Unicode ; après un mot qui finit par une lettre accentuée (é, è, à) suivie de s, t, c, d, l, m, n ou j, il insère une apostrophe : « torsadés'et », « après'une », « liés'à », « habitués'ont ». Mesure corrigée après vérification (le comptage initial, ≈ 45 %, incluait à tort « quelqu'un ») : 24 % des sorties brutes du banc (201 scripts sur 823, 230 blocs sur 9 278) et 13 % des scripts français en base (5 sur 38). Corrigé dans la PR #61 du dépôt web (brouillon).
- **Levier non testé** : `reasoning_effort: low`. Le modèle écrit court par défaut quelles que soient les consignes de longueur ; passer à `medium` coûte des jetons et doit être mesuré.
- **Deux appels par génération** : 98 % des générations en font deux (la première tentative est presque toujours rejetée).

## 7. Limites

60 générations par variante ; un seul modèle (`gpt-5-mini`), un seul profil/langue/plateforme (standard, français, TikTok) ; juge LLM de la même famille que le générateur, sensible à la longueur ; relecture humaine limitée à 5 paires lues par l'auteur de l'expérience ; coût estimé, pas mesuré ; aucun test en production.
