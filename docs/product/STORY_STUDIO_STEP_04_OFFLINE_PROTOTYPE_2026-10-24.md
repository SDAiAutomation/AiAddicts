# Story Studio — étape 4 : prototype 2D offline

Date : 2026-10-24.

## Résultat vérifié localement
Un prototype de 9,5 secondes, 540x960, 24 fps a été produit avec Python Pillow et FFmpeg. Vérification ffprobe : durée 9.500000 secondes ; taille 173457 octets. Deux personnages originaux Néo (renard) et Orion (hibou) apparaissent dans trois échanges. Le rendu anime leurs bras, têtes, corps, clignements et bouches avec des fonctions temporelles déterministes.

Le code et le MP4 sont des **artifacts de conversation locaux**, non encore ajoutés au dépôt GitHub. Le présent document archive les résultats et les limites ; ne pas présenter ce document comme un commit du moteur.

## Ce que cela prouve
- Génération d'un MP4 vertical sans API externe payante.
- Animation procédurale à coût marginal faible sur CPU.
- Rendu déterministe avec acteurs réutilisés et texte par scène.
- Réutilisation de FFmpeg, déjà dans la stack Faceloop.

## Ce que cela ne prouve PAS
- Godot/Blender/Rive non installés ni benchmarkés ; Pillow est un spike provisoire, pas un moteur de production recommandé.
- Aucune voix réelle, aucun alignement audio, aucun visème phonétique.
- Aucune articulation riggée, interpolation de poses de production, occlusion, mouvement complexe, caméra professionnelle.
- Aucune intégration worker, base de données, crédits, authentification ou E2E.
- Aucun test de charge ou de qualité perceptuelle.

## Prochaine étape
1. Versionner le code de prototype et ses tests dans une branche de développement isolée, sans activer la production.
2. Ajouter un contrat JSON `story_animation_v1` et tests offline.
3. Réaliser un vrai benchmark Godot et Blender headless avec les mêmes plans.
4. Brancher une voix locale de test (non payante) et mesurer le lip-sync ; ajouter TTS ElevenLabs uniquement après autorisation.
5. GO/NO-GO sur qualité, coût et maintenance.

## Confidentialité
Le bucket `content-videos` était initialement public selon migration ; un script `activate_private_generate.py` permet de le passer en privé après vérifications, mais l'état réel n'a pas été lu. Ne pas lancer de rendu sur l'environnement partagé tant que non vérifié.
