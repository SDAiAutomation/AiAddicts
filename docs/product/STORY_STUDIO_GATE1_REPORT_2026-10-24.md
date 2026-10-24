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

## Gate 1B — mêmes animations, art généré par l'API OpenAI de Faceloop (2026-10-24)
Livrable : `experiments/story_gate1/pip_gate1b_540x960.mp4` (7,04 s, 24 fps, 540×960, sans audio). Même scénario et même caméra que Gate 1.

- **Chaîne** : 7 images `gpt-image-1-mini` qualité basse (fiche personnage sur fond vert, 3 expressions dont 1 rejetée par la modération, décor d'usine, réveil à visage) → détourage local (`art/key.py`) → découpe en pièces (`art/cut.py` : tête ×3 expressions, torse, gants, chaussures, chapeau, réveil) → montage en marionnette dans Godot (`scene2.gd`) : bras et jambes en lignes d'encre étirables, pièces dessinées pour le reste, calotte du crâne reconstruite en code (le chapeau la masquait dans l'image source), parallaxe, fumée, grain, vignettage.
- **Coût** : ≈ 0,105 USD estimé (table interne du dépôt, non vérifiée en direct) sur 5 USD autorisés. Rendu Godot : ≈ 6-8 s pour 169 images, sans GPU.
- **Verdict visuel [OBS]** : net progrès sur le style et le décor par rapport à Gate 1. Défauts restants : yeux et bouches ne sont que 3 têtes fixes (pas de lip-sync réel), pas de gros plan de corps entier, bras tubulaires un peu rigides, petites aspérités à la jonction calotte/tête, le réveil ne suit pas le personnage du regard, pas de bruitage.
- **Limites** : résolution 540×960 seulement ; dérive de design entre les têtes générées (moustache perdue sans consigne explicite) ; la modération d'OpenAI a refusé 3 requêtes de variantes ; droits d'usage commercial des images non vérifiés ; les sprites générés ne sont pas committés (`sprites/` ignoré) tant que l'utilisateur n'a pas validé.

## Gate 2 — dialogue, deuxième personnage, lip-sync mesuré (2026-10-24)
Livrable : `experiments/story_gate1/pip_gate2_dialogue_540x960.mp4` (14,78 s, 24 fps, 540×960, avec audio). Deux personnages originaux : **Pip** (employé anxieux, noeud rouge) et **Madame Rosette** (commerçante, fleur rouge), un réveil à visage, trois plans (deux personnages, gros plan Pip, final avec poursuite).

- **Dialogue** : 3 répliques en français (« Monsieur Pip, votre réveil sonne encore ! » / « Impossible, madame ! Je l'ai réglé hier ! » / « Alors pourquoi il vous poursuit ? »).
- **Audio [OBS]** : voix **provisoires gratuites** (Windows SAPI « Hortense », deux timbres par changement de hauteur, `audio/make_audio.py`). Durées **mesurées** sur les fichiers : 4,00 s / 4,23 s / 3,05 s ; piste mixée de 14,776 s, vidéo de 14,776 s (`ffprobe`). Les voix finales devront passer par le chemin TTS de Faceloop (payant, accord requis).
- **Lip-sync** : pour chaque image à 24 fps, l'enveloppe RMS de l'audio décide d'une classe de bouche (fermée / ouverte / ronde), avec suppression des clignotements d'une image. Rosette : bouches dessinées en code sur une tête dont le sourire a été effacé (les variantes générées dérivaient : visage redessiné à chaque fois). Pip : 3 têtes générées (fermée, ouverte, ronde). **Limite : la synchro est construite par le calcul, pas évaluée à l'oreille ; seul l'utilisateur peut juger si elle est convaincante.**
- **Interaction** : Rosette parle avec gestes de mains sur les syllabes accentuées ; Pip réagit (inquiétude, mains levées) à la fin de sa réplique ; gros plan quand il répond ; le réveil sonne et saute, Pip s'enfuit.
- **Coût** : ≈ 0,195 USD estimé d'images au total sur 5 USD (≈ 0,09 USD pour ce Gate : personnage 2, variantes de bouche, essais masqués inutiles). Aucun service payant supplémentaire. Rendu Godot ≈ 13-20 s pour 355 images, sans GPU.
- **Défauts honnêtes** : marionnette encore raide (bras tubulaires, poses peu variées), pas de bruitage ni de musique, les mains de Rosette croisent parfois le réveil, la couche de maquillage « cheek lines » du visage de Rosette reste un peu visible, résolution 540×960.
- **Décision proposée** : GO pour Gate 3 (15-30 s, ≥ 3 plans, deux personnages récurrents) si le résultat te paraît acceptable ; la priorité artistique reste d'améliorer le mouvement du corps et d'ajouter décors et plans.

### Gate 2 — mise à jour : voix ElevenLabs (via la clé Faceloop, décision chef de projet)
Livrable : `experiments/story_gate1/pip_gate2_dialogue_elevenlabs_540x960.mp4` (10,08 s, 24 fps, 540×960, avec audio). Remplace les voix provisoires Windows.
- **Voix** : Pip = « Corentin (GrowthOS) » (voix française de Faceloop), Rosette = « Matilda » (voix multilingue), modèle `eleven_multilingual_v2` comme `growthos/engine/tts.py` (stability 0,4 et style 0,35 pour un peu plus de jeu que le défaut produit).
- **Coût [OBS]** : **115 caractères** consommés sur un plafond de 3 000 fixé pour le test (compte Creator : 30 043 / 121 032 utilisés avant l'appel, lu sur l'API d'abonnement). Journal : `out/eleven_ledger.json`.
- **Durées mesurées** : 2,42 s / 2,46 s / 1,90 s ; piste et vidéo de 10,080 s.
- **Lip-sync** : l'API `with-timestamps` fournit l'alignement par caractère ; voyelles ouvertes (a, e, i…) → bouche ouverte, voyelles arrondies (o, u, ou) → ronde, b/m/p/f/v → fermée, les silences de l'enveloppe audio forcent la bouche fermée. Toujours à juger à l'oreille et à l'œil par l'utilisateur.
