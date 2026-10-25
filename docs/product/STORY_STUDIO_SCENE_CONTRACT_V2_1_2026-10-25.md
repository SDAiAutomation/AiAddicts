# Story Studio — contrat de scène v2.1 (animation_schema_version 2) et adaptateur Standard

Gate 2. Étend `STORY_STUDIO_ANIMATION_CONTRACT_V1_2026-10-24.md` **sans le casser** : une histoire en schéma 1 se valide et se rend exactement comme avant (42 cas partagés Python/TypeScript inchangés ; seule la valeur « schéma inconnu » passe de 2 à 3). Code : `growthos/engine/story_animation/contract.py`, miroir `growthos-web/src/lib/story-studio/animation-contract.ts`, adaptateur `story_adapter.py`. Aucun appel payant, rien de déployé ni d'activé.

## 1. Ce qui est nouveau en schéma 2
| Champ | Où | Règle |
| --- | --- | --- |
| `duration_target_s` | histoire | l'une de **60, 90, 120, 180** (300 reste réservé tant qu'un rendu de cette durée n'est pas mesuré). Le texte doit permettre d'atteindre la cible : estimation au débit rapide (17,1 car/s, mesuré) ≥ max(60 s, 0,85 × cible), et au débit lent (14 car/s, estimation prudente du moteur) ≤ 1,3 × cible. Refus **avant tout crédit**. |
| `narrator` | histoire | `{id, name, voice_id}` ; une voix sans corps ; l'identifiant diffère de ceux des personnages. Un plan du narrateur peut afficher les personnages à l'écoute, ou le décor seul (`actors` vide) ; il ne peut pas être un `close_up` (aucun locuteur à cadrer). |
| `editorial` | histoire | `kind` : `fiction`, `educational` ou `mixed` ; `genre` (liste fermée de 14 genres) ; `sources[]` (au plus 20 : `id`, `title`, `author`, `year`, `url` en https, `verification` : `primary`, `secondary` ou `unverified`) ; `disclaimer` (obligatoire pour `mixed` : la fiction est annoncée comme fiction). |
| `nature` | plan | `fact`, `interpretation`, `hypothesis` ou `fiction`. Un plan `fact` doit citer au moins un `source_ids` (identifiants de `editorial.sources`). Une histoire `kind: fiction` n'admet ni fait, ni interprétation, ni hypothèse. |
| Limites | histoire | schéma 2 : au plus **40 plans**, **3 600 caractères** de dialogue, **200 s** estimées (cible maximale 180 s + 10 %). Schéma 1 : 12 plans, 1 200 caractères, 60 s, inchangés. |

Tout champ du schéma 2 présent dans une histoire de schéma 1 est refusé avec le message `requires animation_schema_version 2`. Les champs non pris en charge par le rig (regards, état émotionnel avant/après, continuité d'accessoires) **ne sont pas ajoutés** : un champ sans effet produirait un rendu silencieusement faux. Ils restent à faire avec le rig (Gate 3).

## 2. Durée mesurée sur le fichier final
`quality.judge_media` reçoit `expected["target_s"]` quand une cible existe : **bloquant** (clip non livré, crédit remboursé) sous 60 s ; **à revoir** (clip livré dans l'état `quality_check`) hors de la bande 0,85 à 1,2 × la cible. Sans cible, aucun changement. Le worker (`assembler._run_animated`) passe la cible.

## 3. Pipeline et scène
`pipeline.run` : voix et rôle du narrateur (rôle `narrator` dans la chronologie, aucune bouche animée), limite de durée selon le schéma (`timeline.build_timeline(max_total=...)`), plafond absolu de 200 s côté rendu. `scene.gd` : un plan de narrateur sans acteur est centré sur le décor. Vérifié en local (Godot, 7 plans dont un sans acteur) : rendu sans erreur, sous-titres affichés, personnages à l'écoute en pose de repos.

## 4. Adaptateur Standard → scènes (`story_adapter.adapt`)
Pas de second moteur narratif : un script Standard (`title`, `niche`, `account`, `blocks` hook/point/cta) est **validé par le validateur Standard** (`script.validate_script`), analysé par les **diagnostics de rétention Standard** (`retention.analyze`, rapportés, jamais bloquants), puis traduit : découpage des blocs trop longs aux fins de phrase (≤ 400 caractères par plan), narrateur par défaut, personnages à l'écoute, `shotType` Standard repris (`pov` devient `medium`), changement de décor aux blocs `establish`, `reveal`, `payoff`. Indications facultatives sur un bloc (ignorées par Standard) : `speaker`, `setting`, `acting`, `nature`, `source_ids`. Le résultat est validé par le contrat v2.1 ; ses erreurs sont retournées, pas masquées.

## 5. Les trois scénarios du Gate 1 comme fixtures
`fixtures/story_v21_la_file.json`, `story_v21_parapluie.json`, `story_v21_ville_sans_mots.json` (15, 16 et 16 plans, 1 432 / 1 371 / 1 513 caractères, cible 90 s) et `standard_script_la_file.json` (la même histoire au format Standard). Tests : chacun est valide, atteint sa cible au débit rapide, reste dans le budget au débit lent, cite une source pour chaque fait, et traverse **tout le pipeline** avec des ports factices (voix du narrateur utilisée, durée entre 60 et 200 s, un seul crédit réservé).

## 6. Vérifications
Moteur : 148 tests du paquet, plus routage, worker et file équitable ; suite complète : mêmes 3 erreurs **antérieures** (`test_explainer_generators`, `test_explainer_pipeline`, `test_thumbnail`), Standard et Quiz inchangés. Web : 112 tests `story-*` (dont les cas partagés), `tsc` et `eslint` sans nouvelle erreur.

## 7. Limites connues
- Les durées sont des **estimations** ; la vraie durée se mesure sur l'audio final (Gate 4). Le débit de 17,1 car/s vient d'une seule vidéo.
- L'éditeur web produit toujours du schéma 1 ; rien n'est exposé aux utilisateurs.
- Aucun TTS local : un rendu complet de 90 s nécessite soit ElevenLabs (payant, non déclenché), soit l'adaptateur de voix locale du P3.
- Le décor seul (narrateur sans personnage) est statique ; des plans d'insertion animés sont à prévoir (Gate 3).
- Les sources des trois scénarios sont secondaires ou non consultées (marquées `secondary` / `unverified`) : à recouper avant diffusion.
