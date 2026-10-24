# Story Studio â€” Gate 1 : premier rig 2D (rapport d'Ã©tape)

Date : 2026-10-24. Statut : **en attente de jugement visuel de l'utilisateur**. Aucune intÃ©gration Faceloop, 0 â‚¬ dÃ©pensÃ©.

## Livrable
`experiments/story_gate1/pip_gate1_540x960.mp4` â€” 7,04 s, 24 fps, 540Ã—960, sans audio. Personnage original Â« Pip Â» (tÃªte blanche, lunettes rondes, moustache, nÅ“ud papillon rouge), style cartoon annÃ©es 1930 N&B avec un accent rouge. Trois plans : (A) entrÃ©e en marchant, (B) gros plan de surprise puis d'inquiÃ©tude, (C) il montre un rÃ©veil qui sonne, saute, perd son chapeau et s'enfuit. DÃ©cor en couches (ciel, skyline fumante, faÃ§ade, avant-plan), camÃ©ra qui pousse puis recule, grain, vignettage, rayures, clignotement.

## Mesures [OBS]
- Moteur : Godot 4.7.2, `--write-movie` puis FFmpeg ; poste i3-1005G1, 8 Go, sans GPU dÃ©diÃ©.
- Rendu : 9 Ã  16 s pour 169 images Ã  540Ã—960 (â‰ˆ 1,3-2,3Ã— le temps rÃ©el). Rendu sans GPU **faisable**.
- ItÃ©rations : 3 rendus visionnÃ©s (v1 trop proche d'un personnage connu : redessinÃ© avec tÃªte blanche, lunettes, moustache ; v2 : dÃ©fauts de bouche/Ã©chelle ; v3 : version livrÃ©e).

## Verdict honnÃªte
- **Atteint** : un style cohÃ©rent, des plans variÃ©s, un acting lisible (surprise, inquiÃ©tude, saut, chapeau), des objets animÃ©s avec visage, une ambiance Â« vieux dessin animÃ© Â».
- **Non atteint** : le niveau des rÃ©fÃ©rences. Corps trapu, jambes et bras courts, mouvement de marche peu convaincant en plan large, contours qui Â« bouillonnent Â» de faÃ§on un peu sale, pas de vrais gestes de corps complet ni d'accessoires manipulÃ©s. Le plafond de cette piste dÃ©pend du travail de dessin, que je fais ici par code.
- **Limite technique** : `--resolution 1080x1920` a rendu en 540Ã—960 sur ce poste ; le rendu final en haute dÃ©finition n'est pas rÃ©solu.
- **Audio, dialogue, lip-sync** : hors Gate 1.

## DÃ©cision proposÃ©e
**GO conditionnel pour Gate 2 sur la piste rig 2D seulement si tu juges le style acceptable.** Si le niveau Â« rÃ©fÃ©rences Â» est exigÃ©, il faut tester la piste imageâ†’vidÃ©o (coÃ»t Ã  chiffrer, accord requis) ou prÃ©voir un illustrateur pour les assets.

## Gate 1B — mêmes animations, art généré par l'API OpenAI de Faceloop (2026-10-24)
Livrable : `experiments/story_gate1/pip_gate1b_540x960.mp4` (7,04 s, 24 fps, 540×960, sans audio). Même scénario et même caméra que Gate 1.

- **Chaîne** : 7 images `gpt-image-1-mini` qualité basse (fiche personnage sur fond vert, 3 expressions dont 1 rejetée par la modération, décor d'usine, réveil à visage) ? détourage local (`art/key.py`) ? découpe en pièces (`art/cut.py` : tête ×3 expressions, torse, gants, chaussures, chapeau, réveil) ? montage en marionnette dans Godot (`scene2.gd`) : bras et jambes en lignes d'encre étirables, pièces dessinées pour le reste, calotte du crâne reconstruite en code (le chapeau la masquait dans l'image source), parallaxe, fumée, grain, vignettage.
- **Coût** : ˜ 0,105 USD estimé (table interne du dépôt, non vérifiée en direct) sur 5 USD autorisés. Rendu Godot : ˜ 6-8 s pour 169 images, sans GPU.
- **Verdict visuel [OBS]** : très net progrès sur le style et le décor par rapport à Gate 1. Défauts restants : yeux et bouches ne sont que 3 têtes fixes (pas de lip-sync réel), pas de gros plan de corps entier, bras tubulaires un peu rigides, petites aspérités à la jonction calotte/tête, le réveil ne suit pas le personnage du regard, pas de bruitage.
- **Limites** : résolution 540×960 seulement ; dérive de design entre les têtes générées (moustache perdue sans consigne explicite) ; la modération d'OpenAI a refusé 3 requêtes de variantes ; droits d'usage commercial des images non vérifiés ; les sprites générés ne sont pas committés (`sprites/` ignoré) tant que l'utilisateur n'a pas validé.
