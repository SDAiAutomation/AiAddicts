# Quiz — présentation Motion V1

## Choix produit

`quiz.presentation` accepte `classic` (valeur par défaut) ou `motion`. Une valeur inconnue est rejetée. Les scripts existants sans ce champ gardent le rendu classique. La présentation est indépendante du thème et du choix des illustrations.

Le sélecteur « Mise en scène » est ajouté dans le dépôt frontend `growthos-web`, dans le wizard Quiz et l'éditeur Quiz. `parseQuiz` valide et conserve le champ. La régénération des questions conserve les réglages du Quiz. Aucune migration SQL : la valeur appartient au JSON du script existant. Les séries historiques restent classiques ; aucun réglage de série n'a été ajouté.

## Rendu livré

- Ouverture et conclusion typographiques reprenant le sujet du Quiz.
- Choix animés depuis un point commun vers des rangées stables.
- Compte à rebours vectoriel, calé sur la pause réelle de la narration.
- Révélation avec coche, couleur et déplacement du libellé de la réponse.
- Fenêtre réservée à l'illustration lorsqu'elle existe ; texte séparé des sous-titres.
- Thèmes existants et styles de sous-titres conservés.

Le moteur génère des événements ASS déterministes dans `engine/quiz_motion.py`, via le dispatch Quiz de `engine/captions.py`. Il emploie le rendu FFmpeg/libass existant, sans nouveau worker, fournisseur ou moteur de montage. Les voix et effets sonores existants restent inchangés. Il n'exécute aucun code produit par un modèle. Le coût API supplémentaire de cette chorégraphie est nul ; son temps CPU est à mesurer sur le worker de production.

La bonne réponse n'influence aucun événement de la phase question. Les entrées sont désactivées si la narration ne laisse pas une seconde avant le temps de réflexion. La durée totale et les pauses ne sont pas rallongées.

## Contrat et coordination

`compile_quiz` normalise le choix et le propage aux blocs, y compris les blocs déjà compilés. Le mode racine est autoritaire lors d'une recompilation. `quiz_motion_version=quiz-motion:v1` identifie le rendu sur les blocs Motion. Le nouveau module est ajouté à la liste de fichiers de `generation_cache.py` afin qu'un correctif visuel invalide les artefacts périmés, selon le mécanisme existant.

L'intégration partagée est limitée à ce dispatch et à la liste du cache. Aucun changement de worker, DB, quota, publication ou contrat AutoEdit. À relire par le propriétaire du pipeline partagé lors de l'intégration. Déployer le moteur avant le frontend : un ancien moteur ignorerait l'option Motion choisie dans une interface plus récente.

## Vérification locale

Commandes :

```text
python -m unittest tests.test_quiz_motion tests.test_quiz tests.test_captions tests.test_quiz_audio tests.test_generation_cache -q
python scripts/preview_quiz.py --presentation motion --resolution 720x1280 --full
python scripts/preview_quiz.py --presentation classic --resolution 720x1280 --full
```

Frontend : TypeScript sans émission et tests Quiz de `scripts/frontend-regressions.test.mjs`. Le vrai composant du sélecteur a été monté dans Chromium avec les traductions FR/EN et le CSS du dépôt : 390 et 1280 px, choix initial, sélection, flèches clavier et absence de débordement. Cette vérification isolée ne remplace pas un parcours authentifié sur le site déployé.

Résultats du 11 octobre 2026 : 65 tests moteur et 10 tests frontend ciblés passent ; `tsc --noEmit --incremental false` passe. Les deux aperçus complets durent exactement 36 secondes. Le cas de quatre réponses longues avec illustration et sous-titres sur deux lignes a été rendu dans les thèmes Studio et Minimal ; l'espacement a été corrigé après inspection. Le contraste du texte de la bonne réponse est choisi selon la luminance du fond.

Les aperçus locaux sont sans voix, avec durées illustratives, et ne prouvent pas la synchronisation perceptuelle d'une vidéo narrée. Le moteur utilise les durées réelles des blocs en production ; les tests vérifient les bornes et l'absence de fuite de la réponse. Les planches contact ont été inspectées ; aucun visionnage temps réel avec son n'est revendiqué.

## Limites explicites

Cette V1 est une présentation animée réutilisable, pas un réalisateur IA qui invente des scènes 3D ou des diagrammes factuels pour chaque question. Aucun appel Opus, Cinetic, Remotion ou génération de musique n'est intégré. L'aperçu interactif des questions dans le frontend reste destiné à la relecture du contenu ; son texte précise que les animations sont appliquées au rendu final. Aucune amélioration de rétention n'est revendiquée.

Les modifications sont locales, non publiées et non déployées. Le rendu classique reste le premier choix.
