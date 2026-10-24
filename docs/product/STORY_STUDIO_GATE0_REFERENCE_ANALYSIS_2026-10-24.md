# Story Studio — Gate 0 : analyse des références et écart avec le prototype rejeté

Date : 2026-10-24. Auteur : Claude Code. Relecture : les images des deux vidéos ont été revues dans une seconde session (60 vignettes à 2 s d'intervalle) ; les observations ci-dessous ont été confirmées, avec deux nuances ajoutées. Statut : **analyse réellement effectuée** sur les fichiers reçus (zip `Faceloop_Story_Studio_Claude_Handoff.zip`, sha256 des MP4 conformes au `MANIFEST.json`).

> Les MP4 et captures **ne sont pas dans ce dépôt** (dépôt public, contenu tiers). Les planches de captures annotées sont conservées localement (`gate0-evidence/`, hors Git) et transmises à l'utilisateur. Ce document ne cite que des timecodes et des descriptions.
> Convention : **[OBS]** = observé sur les images ou mesuré ; **[HYP]** = hypothèse non vérifiée. **Je n'ai pas pu écouter l'audio** : voix, intonation, justesse du lip-sync et sound design ne sont donc évalués que par mesures et par image, jamais « à l'oreille ».

## 1. Fiche technique mesurée

| | Te voilà casé | C'est garanti |
| --- | --- | --- |
| Durée | 121,2 s (dont carte de fin TikTok ≈ 118,2–121,2 s) | 99,1 s (dont carte de fin ≈ 95–99 s) |
| Vidéo | H.264, 512×910, 30 fps | idem |
| Audio | AAC 44,1 kHz | idem |
| Loudness intégrée | −11,9 LUFS, LRA 3,0 LU, crête +0,1 dBFS | −11,4 LUFS, LRA 4,5 LU, crête +0,1 dBFS |
| Silences > 0,2 s (seuil −35 dB) | aucun avant la carte de fin | 10 courtes pauses (0,2–1,35 s) entre 1,4 et 24 s, 4 vers 88–92 s, puis la fin |

[OBS] Les deux vidéos sont des **ré-encodages TikTok** : bandeau titre noir en haut (titre + sous-titre entre parenthèses), image utile **4:3 (≈ 512×380, y ≈ 265–645)** au milieu d'un canevas 9:16, incrustation TikTok. L'image utile n'occupe qu'environ 42 % du canevas : « 9:16 plein cadre » n'est pas ce que montrent les références.
[OBS] Audio très compressé et fort (≈ −11 à −12 LUFS, crêtes à 0 dBFS) : cible « TikTok », sans respiration entre les phrases.

## 2. Direction artistique

[OBS] **Deux registres dans la même vidéo.**
- **Cadre narratif en couleur**, style long-métrage/télé 2D classique : loup en costume rayé bleu marine à cravate rouge, lapin au nœud papillon rouge (Te voilà casé 0:00–0:16 et 1:50–1:56) ; loup + âne roux en bleu de travail (C'est garanti 0:00–0:09 et 1:26–1:34). Contours nets, ombrage cel, lumière chaude de coucher de soleil, décors à profondeur (fenêtre, balcon, toits).
- **Flash-back « explicatif » en noir et blanc années 1930**, style *rubber hose* (membres tubulaires, gants blancs, yeux à pupille). **Accent couleur unique** : rouge pour les maisons (Te voilà casé), or pour les pièces (C'est garanti). Grain de pellicule et vignettage ajoutés. Transition « télé glitchée » à ≈ 0:10 de C'est garanti.
- **Objets animés dotés d'un visage** (banque, calendrier, coffre, tirelire, horloge, presse) : motif récurrent, utilisé pour rendre les concepts abstraits visibles.
- Sous-titres en mots/groupes : jaune sur boîte sombre (flash-back) ou blanc sur boîte (cadre) ; légendes de lieu/date (« Washington, 1919 », « Allemagne, 1889 »).

[OBS] **Cohérence** : le loup, le lapin et l'âne gardent leurs traits d'un plan à l'autre (avec de légères dérives de motif de costume/museau). Les personnages du flash-back N&B sont des **types génériques** (ouvrier à casquette, patron à haut-de-forme, banquier à moustache) qui **ne sont pas** les mêmes individus d'un plan à l'autre : seule la **cohérence de style** est maintenue. **Conséquence produit :** l'identité stricte n'est nécessaire que pour les 1-3 personnages récurrents du cadre ; le reste peut être « cohérent en style » seulement.
[OBS, revérifié 2026-10-24 sur images toutes les 2 s] **Nuance :** dans C'est garanti, un « type » de héros N&B à tête ronde et gants blancs revient dans de nombreux plans (jeune ouvrier, puis variantes), avec dérive de détails d'un plan à l'autre. La cohérence n'est donc pas qu'une cohérence de style, mais elle n'est pas stricte non plus.

## 3. Animation

[OBS] Planche de mouvement (images à 0,25–0,4 s d'intervalle) :
- **Jeu de corps complet** : trois patrons qui secouent la grille d'usine avec tout le corps (Te voilà casé ≈ 0:22–0:25) ; ouvrier qui marche avec un marteau/des planches (0:26–0:28) ; vieil homme qui se balance dans un rocking-chair et souffle une bulle (C'est garanti ≈ 0:30–0:33).
- **Acting du visage** : lapin qui passe de l'enthousiasme à la colère en deux répliques (Te voilà casé ≈ 0:09–0:11), sourcils, regard, bouche à plusieurs formes ouvertes/fermées qui alternent avec la parole.
- **Animation secondaire** : oreilles, fumée, bulles, pièces qui tombent, papiers, feu d'artifice de pièces.
- **Interaction avec des accessoires** : le loup sert une bouteille (1:50–1:52), lit et brandit un livre (1:52–1:56, C'est garanti 1:30–1:34), journal, contrat, parchemin déroulé.
- [OBS] Quelques **dérives typiques d'une génération** : nombre de planches qui change d'une image à l'autre (Te voilà casé ≈ 0:26–0:28), objets qui se déforment. Ces défauts passent à 2-3 s par plan.

**Ce que cela implique** : le niveau cible est une **animation de personnages à corps entier avec accessoires**, pas des poses réutilisables avec une bouche qui bouge. Aucun moteur « marionnette découpée » simple ne reproduit cela sans un travail de rig et d'illustration conséquent.

## 4. Cinématographie et montage

[OBS] Échantillonnage toutes les 2 s : **un nouveau plan à presque chaque échantillon** (≈ 2-4 s par plan ; un détecteur automatique `scene>0,2` n'en a trouvé que 37 et 15 — **sous-estimation évidente** à cause du grain et des fondus, valeur à ne pas utiliser).
- **Échelles de plan** : large d'établissement (Te voilà casé 0:00), **gros plan visage** (0:04, 0:12), plan moyen à deux, **plans d'insertion sur un objet** (livre C'est garanti 1:32 ; maison rouge ; calendrier), **champ/contre-champ** loup–lapin.
- **Continuité** : décors identiques revus à l'identique pour le cadre (fenêtre, table à nappe vichy, balcon).
- **Rythme** : le plan change quand la phrase/idée change ; une idée = un plan = une action lisible.
- Les mouvements de caméra continus (travelling, zoom) n'ont **pas** pu être établis de façon fiable sur les images extraites : **non évalué**.

## 5. Audio

[OBS par mesures] Voix-off continue sans silence notable, énergie large bande jusqu'à ≈ 8 kHz, fortes transitoires verticales sur le spectrogramme alignées avec des changements de plan. [HYP] musique de fond + effets de transition (whoosh/impacts) + narration ; voix de personnages dans le cadre (le loup et le lapin se répondent à l'écran avec sous-titres de dialogue). **Non évalué : timbre, intonation, justesse du lip-sync, mixage voix/musique.** À faire écouter à l'utilisateur.

## 6. Structure narrative

[OBS] Format en 3 temps, identique dans les deux vidéos :
1. **Accroche en dialogue (0–16 s)** : conflit immédiat entre deux personnages récurrents (« Ça y est, ils m'ont accordé… » / « Fini de donner mon argent » ; « Ils ont reculé ma retraite »).
2. **Flash-back explicatif (≈ 0:18 → 1:48 / 0:10 → 1:24)** : histoire d'une idée en séquence de plans-métaphores, chaque plan = une phrase de la narration, avec un lieu/une date en légende.
3. **Retour au cadre + retournement (1:50 → fin / 1:26 → fin)** : le loup apparaît comme celui qui manipule, objet fétiche (le livre « Influencing the Masses »), phrase finale-question (« tu ne te demandes jamais qui l'a mise là »).
Durées : 100–120 s, bien plus long que le format 15–30 s de Gate 3.

## 7. Techniques plausibles [HYP]

| Hypothèse | Indices pour | Indices contre |
| --- | --- | --- |
| **Plans de 2-5 s générés par un modèle image→vidéo** (images-clés + prompt), assemblés avec voix-off et sous-titres automatiques | dérives d'objets d'une image à l'autre ; nombre de décors/castings différents par minute ; objets personnifiés ; durée courte des plans ; variations légères de costume pour les personnages récurrents | aucune preuve directe (pas de métadonnées exploitables ; je n'ai pas recherché de filigrane) |
| Animation 2D traditionnelle/rig | style de dessin très maîtrisé | volume (≈ 40-60 décors et actions neufs par vidéo) incompatible avec un coût de production artisanal |
| Hybride : images-clés IA + animation 2.5D/rig + compositing | possible pour les plans objets simples | le jeu de corps complet observé dépasse un simple parallaxe |

[OBS, revérifié] Indices supplémentaires de génération : bras très étirés ou fusionnés, couverture de livre approximative, objets qui changent de forme d'un plan à l'autre. Indices compatibles avec l'hypothèse image→vidéo, **pas une preuve**.
**Conclusion prudente :** la qualité des références est compatible avec de la **vidéo générative image→vidéo, guidée par des images de référence pour les personnages récurrents**. Rien ne permet de l'affirmer. Gate 1 testera l'hypothèse au lieu de la supposer.
**Droits :** les designs (loup à costume rayé, lapin à nœud, âne) rappellent des archétypes de dessin animé connus. **Ne rien copier** : Gate 1 utilisera des personnages et un langage visuel originaux.

## 8. Écart avec le prototype Néo/Orion rejeté (PR #72)

J'ai **régénéré** le MP4 du prototype (code de la PR #72, Pillow + FFmpeg, 540×960, 9,5 s) et examiné ses images. Notes de 0 à 5, **jugement subjectif de l'auteur**, à contester :

| Axe | Référence | Prototype #72 | Écart |
| --- | --- | --- | --- |
| Style/finition | contours, ombrage cel, grain/lumière, deux registres | formes géométriques plates, un seul fond statique avec lune | 4 vs 1 |
| Design personnages | expressifs, silhouettes distinctes | ronds/ovales symétriques, bras en bâtons | 4 vs 1 |
| Animation corps | acting complet, secondaire | mêmes poses, bras qui oscillent en sinus (« flottement générique ») | 4 vs 0-1 |
| Visage | expressions variées, regards | 1 paire d'yeux fixes, bouche ouverte/fermée, clignements périodiques | 4 vs 1 |
| Cinéma | 5+ échelles de plan, champ/contre-champ | **une seule composition fixe, aucune caméra, aucun cut** | 4 vs 0 |
| Décors | profondeur, détails, continuité | colline + ciel uniforme | 4 vs 0 |
| Interaction/accessoires | bouteille, livre, objets | aucun | 4 vs 0 |
| Texte | sous-titres propres | **boîte UI + texte qui se chevauche** (« Orion, comment savoir si une idée est vraiment… » superposé) | défaut visible |
| Audio | voix + musique + SFX | **muet** | – |

[OBS] Le prototype confirme le rejet de l'utilisateur. Il prouve seulement qu'un MP4 vertical peut être produit sans API. **Le rendu procédural par primitives Pillow est NO-GO comme voie artistique** ; je le classe comme contre-exemple. Autres constats : le CI de la PR #72 est **rouge** (`ffmpeg: command not found` sur le runner), donc même le « smoke test » annoncé n'a jamais été vert.
