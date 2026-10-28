# Story Studio — rendu « storyboard » (2026-10-28)

Statut : implémenté derrière `STORY_RENDERER` (défaut `storyboard`), testé hors ligne uniquement (fournisseurs simulés). **Aucun rendu réel n'a encore été produit ni jugé.**

## Quoi

Un second moteur de rendu pour les histoires animées, à côté de `rig_v1` (marionnettes Godot) :

1. **Beats sur l'audio mesuré** (`story_animation/beats.py`) : après la synthèse vocale et la timeline mesurée, chaque réplique est coupée en idées de 2 à 4 s aux fins de proposition/ponctuation, calées sur l'alignement caractère du fournisseur (sinon au prorata des caractères). Jamais de mot coupé ; une réplique courte (< 4,6 s) reste un seul beat ; une phrase courte entière peut rester seule (nouvelle phrase = nouvelle idée).
2. **Mise en scène par beat** (`story_animation/direction.py`, prompt versionné `storyboard-direction/1.0.0`) : **un seul** appel LLM par histoire (OpenAI chat completions, modèle `STORY_DIRECTOR_MODEL`, défaut `gpt-5-mini`) qui renvoie pour chaque beat : ce que l'image montre, l'échelle de plan (`wide|medium|close_up|insert`), le mouvement (`push_in|pull_out|pan_left|pan_right|static|shake`), les personnages récurrents présents (par id) et des figurants génériques (liste fermée de « types »). Réponse validée strictement (enums fermés, ids connus, longueurs bornées, caractères de contrôle retirés), réparée champ par champ, sinon repli déterministe ; variété imposée (pas trois échelles identiques de suite, pas deux mouvements identiques de suite, changements de section rares). Rien dans la réponse ne sert de chemin, d'URL ni de commande.
3. **Une image par beat** (9:16) via la chaîne Standard : `openai_images.generate_image` + `image_model_router.select_model("final")`, prompt = `image_prompt_builder.build_scene_prompt` avec la Style Bible de l'histoire (`image_style_bible.resolve_story_style_bible` : `noir_1930`, `sepia_1930`, `cyanotype_1930`, `couleur_1930`) et la fiche personnage **conditionnelle** des seuls personnages présents (`image_character_bible`). Fiches : `script.characters[].description` si présente, sinon le look du pack (Pip : grosse tête ronde blanche, lunettes rondes, moustache noire, chapeau melon, nœud papillon rouge ; Rosette : chapeau noir à fleur rouge). Jamais de texte dans l'image.
4. **Montage** : Ken Burns par beat selon son mouvement (helpers de `engine/video.py`, nouveau mouvement `shake`), coupes franches entre idées, fondu de 0,12 s seulement aux changements de section (`transition_in: fade` de l'histoire ou `section_start` du LLM), grain de pellicule selon le style + vignette, voix narration/dialogues de la timeline mesurée mixées comme `rig_v1` (`voices.mix_and_mux`, loudnorm −16 LUFS).
5. **Sous-titres** : presets Standard de `engine/captions.py`, `script.caption_style` (ids de `_CAPTION_STYLES`, `off` = aucun sous-titre incrusté, inconnu/absent → `caption_style_or_default`). L'ancien chemin `subtitles.py` (boîte grise) n'est pas utilisé.
6. **Clip clé (seam)** : `StoryboardPorts.key_clip` (défaut `None`) peut remplacer jusqu'à `max_key_clips` beats par un clip image→vidéo ; le clip doit être un fichier vidéo dans le dossier du job. Aucun fournisseur vidéo n'est implémenté ici ; son coût doit être déclaré dans `key_clip_usd` avant activation.

## Pourquoi

Verdict du propriétaire sur le premier rendu réel `rig_v1` : deux personnages côte à côte dans la même pose, ~7 s par plan, presque pas de gros plans ni d'inserts, des actions racontées jamais montrées, sous-titres en boîte grise. Les références (`STORY_STUDIO_GATE0_REFERENCE_ANALYSIS_2026-10-24.md`) : une idée = un plan de 2-4 s, objets-métaphores à visage, inserts/gros plans/plans larges, rubber hose N&B à accent unique, grain, figurants « types », 1-3 personnages récurrents stricts.

## Argent

- Ordre inchangé : refus (contrat, accès, modération, disponibilité, budget) **avant** la réservation du crédit ; voix, LLM et images **après** ; tout échec après la réservation rembourse une fois ; publication = succès.
- L'estimation avant crédit ajoute au coût des voix : `max_images = ceil(durée estimée / 2,5 s)` (plafond 90) images + 20 % d'essais supplémentaires (min. 2), et 2 appels LLM au plus. Après la découpe, les beats sont fusionnés pour ne jamais dépasser `max_images` ; les appels image sont bornés globalement (2 essais par beat, en plus des reprises transitoires du client). Contrôlé contre `story.budget.max_usd` **et** un plafond serveur `STORY_STORYBOARD_MAX_USD` (défaut 8 $).
- Prix image estimé depuis les tarifs tokens de l'environnement (`IMAGE_PRICE_*`, ajoutés au workflow, identiques au worker principal), sinon 0,08 $ par image. Prix LLM réel calculé depuis les tokens si `STORY_DIRECTOR_PRICE_*` est configuré, sinon inconnu (jamais 0).
- Événements : `generation_started` (renderer, coût estimé, plafond d'images) et `generation_completed` (renderer, beats, images, images réutilisées, source de la mise en scène, appels LLM, style de sous-titres, versions).

### Coût estimé pour 100 s (estimation, pas une facture)

| Poste | Plafond vérifié avant crédit | Attendu |
| --- | --- | --- |
| Voix (~1 400-1 700 caractères à 0,18 $/1k) | ~0,25 $ | ~0,29 $ |
| Images (gpt-image medium portrait ≈ 0,052 $) | 48 × 0,052 ≈ 2,50 $ | ~32 × 0,052 ≈ 1,65 $ |
| Mise en scène LLM | 0,10 $ (réserve) | ~0,01 $ |
| **Total** | **≈ 2,85 $** | **≈ 1,95 $** |

Durée de job estimée : images espacées de 13 s par le client (≈ 7-9 min pour 32-40 images) + montage (Ken Burns sur-échantillonné, ≈ 3× la durée vidéo sur un runner standard, non mesuré sur le runner).

## Qualité et repli

- Une image qui échoue après ses essais réutilise l'image voisine avec un autre recadrage/mouvement ; plus de 30 % d'images réutilisées → la vidéo part en `quality_check` (revue humaine). Aucune image du tout → échec et remboursement.
- Mise en scène entièrement en repli déterministe → `quality_check`.
- Contrôle média existant (`measure` + `judge_media`) : 1080×1920, 25 i/s, durée image = durée son, noirs, gel, volume, taille (CRF 28 en passe finale, le grain coûte cher).

## Limites connues

- Animation = caméra sur image fixe (Ken Burns), pas de jeu de corps : le seam `key_clip` est prévu pour les beats clés.
- Cohérence des personnages par texte seulement (pas d'image de référence), dérive possible d'un plan à l'autre.
- Le 4:3 centré des références n'est pas reproduit (plein cadre 9:16).
- Pas de musique ni de bruitages (comme `rig_v1`).
- Le workflow télécharge encore Godot et les packs (utile pour revenir en arrière) même en mode storyboard.
- Non vérifié : rendu réel avec de vraies images et de vraies voix, durée réelle du job sur le runner, adhérence réelle du modèle d'image au style et aux fiches personnages, jugement artistique.

## Revenir aux marionnettes

Variable de dépôt GitHub `STORY_RENDERER=rig_v1` (lue par `.github/workflows/story-animation-worker.yml`), ou variable d'environnement `STORY_RENDERER=rig_v1` sur le worker. Aucun changement de code ; le chemin `rig_v1` est inchangé.
