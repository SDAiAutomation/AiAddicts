# Story Studio — Gate 1 : premier rig 2D (rapport d'étape)

Date : 2026-10-24. Statut : **en attente de jugement visuel de l'utilisateur**. Aucune intégration Faceloop, 0 € dépensé.

## Livrable
`experiments/story_gate1/pip_gate1_540x960.mp4` — 7,04 s, 24 fps, 540×960, sans audio. Personnage original « Pip » (tête blanche, lunettes rondes, moustache, nœud papillon rouge), style cartoon années 1930 N&B avec un accent rouge. Trois plans : (A) entrée en marchant, (B) gros plan de surprise puis d'inquiétude, (C) il montre un réveil qui sonne, saute, perd son chapeau et s'enfuit. Décor en couches (ciel, skyline fumante, façade, avant-plan), caméra qui pousse puis recule, grain, vignettage, rayures, clignotement.

## Mesures [OBS]
- Moteur : Godot 4.7.2, `--write-movie` puis FFmpeg ; poste i3-1005G1, 8 Go, sans GPU dédié.
- Rendu : 9 à 16 s pour 169 images à 540×960 (≈ 1,3-2,3× le temps réel). Rendu sans GPU **faisable**.
- Itérations : 3 rendus visionnés (v1 trop proche d'un personnage connu : redessiné avec tête blanche, lunettes, moustache ; v2 : défauts de bouche/échelle ; v3 : version livrée).

## Verdict honnête
- **Atteint** : un style cohérent, des plans variés, un acting lisible (surprise, inquiétude, saut, chapeau), des objets animés avec visage, une ambiance « vieux dessin animé ».
- **Non atteint** : le niveau des références. Corps trapu, jambes et bras courts, mouvement de marche peu convaincant en plan large, contours qui « bouillonnent » de façon un peu sale, pas de vrais gestes de corps complet ni d'accessoires manipulés. Le plafond de cette piste dépend du travail de dessin, que je fais ici par code.
- **Limite technique** : `--resolution 1080x1920` a rendu en 540×960 sur ce poste ; le rendu final en haute définition n'est pas résolu.
- **Audio, dialogue, lip-sync** : hors Gate 1.

## Décision proposée
**GO conditionnel pour Gate 2 sur la piste rig 2D seulement si tu juges le style acceptable.** Si le niveau « références » est exigé, il faut tester la piste image→vidéo (coût à chiffrer, accord requis) ou prévoir un illustrateur pour les assets.
