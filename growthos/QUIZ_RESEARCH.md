# Quiz Faceloop — recherche et première amélioration

Recherche du 1er octobre 2026. Codex prend en charge les quiz, selon l'instruction utilisateur de cette date.

## Conclusion

Le meilleur axe de travail est un quiz immédiatement compréhensible, agréable à jouer et dont chaque réponse apporte une récompense. La durée idéale, le nombre de questions et la longueur du compte à rebours restent à tester sur nos propres vidéos. Les données publiques ne donnent pas accès à la rétention des concurrents.

## Échantillon et limites

- vidIQ : 15 Shorts aux titres anglais, recherche « quiz guess trivia », fenêtre six mois, classement par surperformance de la chaîne.
- vidIQ : recherche française séparée, 2 résultats, classés par vitesse de vues. Cette métrique n'est pas comparable au score de surperformance anglais. L'outil outliers ne prend pas en charge les Shorts français.
- Comparaison avec les 50 Shorts récents de Crazy Quiz, y compris les performances modestes. Aucune chaîne personnelle n'a été interrogée.
- Trois analyses vidéo détaillées ont été demandées. Elles restent en cours chez vidIQ après plus de dix minutes : aucune affirmation sur le montage ou le son des références n'en est tirée. Les identifiants de reprise et derniers états sont conservés localement dans `output/quiz-preview/research-jobs.json` ; reprendre par polling, sans soumettre de nouvelles analyses payantes.
- Biais : sélection de succès, couverture limitée du français, âge des vidéos variable, baseline vidIQ non documentée dans la réponse. Les ratios extrêmes des petites chaînes sont fragiles. Les chaînes distinctes ne garantissent pas des propriétaires indépendants.
- Appels facturés déclarés par vidIQ : 45 crédits (recherches 10, catalogue 5, analyses vidéo 30). Aucun crédit de génération Faceloop utilisé.

Les résultats publics et filtres sont conservés dans [le relevé JSON](docs/research/quiz-2026-10-01.json). Les chiffres ci-dessous sont des instantanés du 1er octobre, pas des prévisions.

## Exemples utiles

| Référence | Publication | Durée | Vues | Signal vidIQ | Ce qu'elle permet de proposer |
| --- | --- | --- | ---: | --- | --- |
| [Crazy Quiz — animaux](https://www.youtube.com/shorts/oP8oTy803BA) | 09/09/2026 | 83 s | 446 868 | Surperformance 140,73 | Tester un défi sur un thème familier. Détails visuels à confirmer. |
| [Crazy Quiz — autre quiz animaux](https://www.youtube.com/shorts/oLvPtK3zcD0) | 16/09/2026 | 76 s | 202 021 | Surperformance 87,46 | Deux succès dans une même chaîne ; ce ne sont pas deux sources indépendantes. |
| [GeeTriv — logos](https://www.youtube.com/shorts/5nXAzM1qt-c) | 17/09/2026 | 98 s | 94 381 | Surperformance 65,44 | Piste de reconnaissance visuelle, avec un très petit compte de 135 abonnés au relevé. |
| [Eman Quiz — culture générale](https://www.youtube.com/shorts/8LVJ5DMFQ2Y) | 21/09/2026 | 71 s | 126 532 | Surperformance 7,96 | Le quiz de connaissances reste une piste pertinente. |
| [Nel G — défi 10/10](https://www.youtube.com/shorts/9pP7m8E9eL0) | 25/09/2026 | 54 s | 96 567 | Environ 730 vues/h | Exemple francophone de promesse de score. Ne valide pas le qualificatif « impossible ». |
| [Alban IRL — pays et continents](https://www.youtube.com/shorts/lX62Z83kdQ0) | 27/09/2026 | 49 s | 25 031 | Environ 466 vues/h | Autre référence francophone, sujet précis. |

**Contre-exemples :** dans la même chaîne Crazy Quiz, [un autre quiz animaux](https://www.youtube.com/shorts/IFUCz4FLboI) du 26 septembre compte 7 360 vues ; [un défi « Only 1% »](https://www.youtube.com/shorts/i4F9gbWsUSs) du 14 septembre en compte 1 958. Le thème ou une accroche spectaculaire ne suffit pas. Parmi les 37 vidéos du catalogue publiées du 1er au 23 septembre inclus, la médiane brute est de 3 264 vues. Ce calcul descriptif n'est ni une comparaison à âge égal, ni la baseline propriétaire utilisée par vidIQ.

La présence de succès de 49 à 98 secondes invalide seulement une règle universelle « tout doit faire moins de 30 secondes ». Elle ne démontre pas qu'allonger un quiz améliore sa performance.

## Ce que les sources officielles étayent

1. **Donner immédiatement une raison de rester.** Dans l'entretien YouTube avec Jenny Hoyos, l'ouverture dès la première seconde est présentée comme décisive. Pour Faceloop, cela motive un test de première question immédiate plutôt qu'une longue introduction. C'est une adaptation éditoriale, pas un résultat expérimental propre aux quiz. [YouTube, 28 janvier 2025](https://blog.youtube/creator-and-artist-stories/youtube-shorts-deep-dive/).
2. **Rendre l'information lisible et le rythme perceptible.** TikTok recommande le vertical, l'espace réservé à son interface, une structure claire et l'usage du son et du mouvement. Ces recommandations portent sur la publicité ; leur transfert aux quiz organiques reste une hypothèse. [TikTok Creative Codes](https://ads.tiktok.com/business/en-US/creative-codes).
3. **Mesurer au-delà des vues.** Observer le choix de regarder plutôt que de passer, les vues engagées et la rétention. Comparer des formats et des durées proches, regarder aussi les échecs. [YouTube — analyse des Shorts](https://support.google.com/youtube/answer/12942217?co=YOUTUBE._YTVideoType%3Dshorts&hl=en), [mesures d'engagement](https://support.google.com/youtube/answer/9313698?hl=en).
4. **Conserver une vraie valeur éditoriale.** YouTube distingue le contenu original des productions répétitives ou fabriquées en masse. Varier uniquement le fond ou quelques noms ne construit pas une expérience originale. [Règles de monétisation YouTube](https://support.google.com/youtube/answer/1311392?hl=en).

## Diagnostic du moteur actuel

- Chaque question cumule une annonce, la question, la lecture des choix, une pause, une formule de réponse et parfois une longue explication. Ce cumul peut expliquer une durée élevée ; aucune perte de rétention n'est mesurée ici.
- L'ancienne mise en page regroupait les choix dans un seul bloc, puis déplaçait la bonne réponse au centre. Les positions fixes réduisent l'effort nécessaire pour retrouver son choix.
- La dernière question était systématiquement annoncée comme la plus difficile, sans mesure ni métadonnée qui le justifie.
- Les visuels d'exemple peuvent montrer la bonne réponse avant la révélation (par exemple Mercure pour une question dont Mercure est la réponse). La direction visuelle devra préserver le jeu.
- `compile_quiz` conserve des blocs déjà compilés. Modifier la narration de ces scripts demandera une recompilation explicite ; le nouveau rendu de cartes s'applique aux blocs existants.
- `generation_cache` inclut déjà `captions.py` et `quiz.py` dans son empreinte. Le changement de code invalide les artefacts selon le mécanisme existant ; une régénération complète peut entraîner des appels payants selon le chemin suivi.

## Première livraison dans le moteur existant

- Cartes de réponse distinctes et de largeur fixe, adaptation des textes longs sans tronquer une réponse.
- Même emplacement des choix avant et après la révélation ; couleur verte et coche pour la bonne réponse.
- Progression question/total, barre de progression, compteur et barre de temps animée pendant la pause réelle du bloc audio.
- Espace laissé à droite et en bas pour l'interface sociale, couleurs des huit thèmes conservées, positions proportionnelles à la résolution.
- Retrait de la promesse non vérifiée de difficulté dans les six langues.
- Aucun nouveau contrat de job, fournisseur ou appel IA. Rendu vectoriel via libass dans le pipeline existant.

Validation : 52 tests ciblés passent dans `venv`, dont légendes, compilation quiz, audio du compte à rebours, cache et champs qualité de l'assembleur. Aperçus FFmpeg de 30 secondes produits localement, inspection des phases question/minuteur/réponse en thème sombre 1080×1920 et de la réponse en thème clair 720×1280. Les autres rapports d'image ont des assertions de position, pas une validation visuelle complète.

Reproduire : `python scripts/preview_quiz.py --theme studio` ou `--theme minimal --resolution 720x1280`. Sorties dans `output/quiz-preview/`. Ces aperçus sont sans voix, avec des durées illustratives ; ils ne valident pas la synthèse vocale ni un job en production. Les vidéos déjà exportées ne sont pas modifiées. Aucun déploiement ou publication effectué.

## Expériences suivantes, à mesurer

| Priorité | Hypothèse | Variante proposée | Mesure |
| --- | --- | --- | --- |
| 1 | Une question immédiatement jouable réduit les départs initiaux | Ouverture sur la question contre introduction actuelle | Choix de regarder et rétention initiale, si disponibles |
| 2 | Le temps utile compte plus que la durée totale | À contenu comparable, réduire les formules répétées ; comparer 3 et 5 s de réflexion pour les questions simples | Rétention pendant réflexion et révélation, lisibilité |
| 3 | Une explication courte rend la réponse satisfaisante | Un fait utile après chaque réponse contre simple confirmation | Rétention jusqu'à la question suivante, retours sur exactitude |
| 4 | Une progression de difficulté donne envie de finir | Facile → intermédiaire → défi, après revue éditoriale réelle | Rétention par question, participation au score |

Préparer des questions originales et vérifier chaque bonne réponse et ses distracteurs. Ne pas reprendre les formulations, visuels ou scripts des références. Ne pas fabriquer de taux de réussite du type « seuls 1 % réussissent ».

Tester une variable à la fois sur des sujets, langues, durées et créneaux comparables. Comparer à âge égal et répéter sur plusieurs vidéos ; les premiers résultats seront directionnels, pas une preuve statistique. Ne pas déduire des chutes à la seconde à partir des vues agrégées. Si les métriques nécessaires sont absentes, les marquer indisponibles.
