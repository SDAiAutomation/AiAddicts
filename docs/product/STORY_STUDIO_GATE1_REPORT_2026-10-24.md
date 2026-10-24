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

## Gate 3 — histoire complète (2026-10-24)
Livrable : `experiments/story_gate1/pip_gate3_story_540x960.mp4` (21,6 s, 24 fps, 540×960 vertical, avec audio, sous-titres incrustés).

- **Histoire** : Madame Rosette accuse le réveil de Pip de sonner depuis ce matin ; il jure l'avoir réglé ; le réveil la suit partout ; Pip : « Il croit que vous êtes en retard ! » ; Rosette : « Depuis quarante ans, je suis à l'heure ! » ; chute : c'est Pip qui est en retard (son déjeuner), il s'enfuit, le réveil le poursuit.
- **Montage [OBS]** : 6 plans (large à deux, gros plan Pip, plan moyen Rosette + réveil, gros plan Pip, gros plan Rosette, large final avec fuite), **points de coupe calculés** au milieu des silences entre répliques (`scene4.gd`), ouverture et fermeture en fondu. Deux personnages récurrents (Pip, Rosette) + le réveil comme troisième « acteur ».
- **Audio** : 6 répliques ElevenLabs (mêmes voix que Gate 2), durées mesurées 3,53 / 2,42 / 1,77 / 1,77 / 4,13 / 3,11 s. **Musique** : fond ragtime **synthétisé localement, composition originale** (pas de bibliothèque tierce, donc aucune licence à vérifier), atténuée pendant la voix (sidechain), sonnerie du réveil synthétisée. Mesure : volume moyen −19,4 dB, crête −0,8 dB.
- **Sous-titres** : 21 groupes de ≤ 3 mots synchronisés sur l'alignement par caractère de l'API, texte crème sur bandeau sombre (volontairement différent du jaune des références).
- **Contrôles automatiques [OBS]** : `blackdetect` et `freezedetect` (ffmpeg) : aucun plan noir ni image gelée hors fondus. Dimensions 540×960, 24 fps, durée vidéo = audio ± 0,06 s.
- **Coût** : ElevenLabs **393 caractères** au total sur un plafond de 3 000 (journal `out/eleven_ledger.json`) ; images : ≈ 0,195 USD d'API OpenAI estimé sur 5 USD ; rendu local ≈ 20 s sans GPU.
- **Défauts honnêtes** : le niveau d'animation reste en deçà des références (marionnette à bras tubulaires, peu de poses, pas de jeu de corps complet avec accessoires), résolution 540×960, pas de bruitage de pas, une seule scène/décor, voix non écoutées par l'auteur, sous-titres avec la police par défaut de Godot, droits d'usage commercial des images générées non vérifiés.
- **Décision proposée** : le prototype prouve qu'une histoire courte cohérente, parlée, sous-titrée et montée peut être produite à coût marginal quasi nul. Il ne prouve pas le niveau « références ». **GO conditionnel pour Gate 4 (intégration)** uniquement si l'utilisateur valide l'esthétique ; sinon améliorer d'abord l'animation corporelle et la variété de décors.

## Gate 3b — corps, décors, résolution (2026-10-24)
Livrable : `experiments/story_gate1/pip_gate3b_story_1080x1920.mp4` (21,6 s, 24 fps, **1080×1920**, audio AAC), même histoire et même audio que Gate 3. Demande de l'utilisateur : « améliorer l'animation des corps, la variété des décors et la résolution avant le Gate 4 ».

- **Résolution [OBS]** : 1080×1920 obtenu en fixant la taille de fenêtre dans `project.godot` et en mettant la scène à l'échelle ×2 (`--resolution` en ligne de commande était ignoré). Rendu Godot ≈ 47 s (≈ 105 s avec encodage), sans GPU. Les sprites sont suffisamment nets ; les décors (1024×1536) sont agrandis ×1,25.
- **Décors** : 4 décors au lieu d'1 — boutique d'horloger (conversation), ruelle d'usine (poursuite), terrasse de café (final). Les 3 nouveaux plans ont été générés pour ≈ 0,045 USD (qualité basse), même style que le premier.
- **Montage** : 8 plans au lieu de 6 (boutique : large, gros plan Pip, plan moyen, gros plan Pip, gros plan Rosette, large de la révélation ; ruelle : poursuite ; café : arrivée), cuts toujours calculés sur l'audio mesuré.
- **Corps** : une série de gestes écrits pour chaque réplique (`scene5.gd`, fonction `act`) — Rosette accuse du doigt une main sur la hanche, se tient le menton en montrant le réveil, poings tremblants et buste qui pompe quand elle s'indigne ; Pip lève les paumes en se défendant, se tord les mains, porte la main au front puis tient sa tête (le chapeau s'envole), s'accroupit en anticipation avant de courir ; marche plus rebondie (écrasement/étirement à chaque pas, bras plus amples) ; réveil qui rebondit en s'écrasant à l'atterrissage et se penche dans le sens du déplacement ; respiration et petits mouvements en continu pour que personne ne soit figé ; léger pompage de la caméra sur les syllabes accentuées.
- **Contrôles [OBS]** : `blackdetect` et `freezedetect` ne signalent rien hors fondus ; durée 21,625 s.
- **Coût** : images OpenAI ≈ 0,24 USD au total (estimation interne) sur 5 USD ; ElevenLabs inchangé (393 caractères, l'audio n'a pas été régénéré).
- **Limites honnêtes** : le jeu de corps reste celui d'une marionnette (poses tenues entre des positions clés, pas d'animation image par image), les expressions faciales se limitent à trois têtes par personnage, les gestes dépendent de coordonnées écrites à la main, le rendu HD multiplie le temps de rendu par ≈ 2,5, droits d'usage commercial des images générées toujours non vérifiés, voix et musique non écoutées par l'auteur.
