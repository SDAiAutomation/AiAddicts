# Story Studio — Gate 4 : plan d'intégration dans Faceloop (document uniquement)

Date : 2026-10-24. Statut : **PLAN. Aucun code produit, aucun déploiement, aucune migration appliquée, aucune écriture en base.** Fait suite à l'approbation visuelle de l'utilisateur sur le clip Gate 3c (« assez bon »). Légende : **[VÉRIFIÉ]** = lu dans le code aujourd'hui ; **[À VÉRIFIER]** = hypothèse ; **[DÉCISION]** = choix qui revient à l'utilisateur.

## 1. Ce que le prototype prouve, et ce qu'il ne prouve pas
- Prouvé : une histoire de ~22 s à 2 personnages, 8 plans, voix, sous-titres, musique et sonnerie, **rendue en 1080×1920 sur un CPU sans GPU en ≈ 1-2 min**, pilotée par une chronologie issue de durées audio **mesurées**.
- Non prouvé : rendu sur le runner Linux de production, coût en minutes de runner, droits d'usage commercial des images générées, qualité à l'échelle (autres personnages, autres décors), résistance aux entrées hostiles.

## 2. Parcours réel actuel [VÉRIFIÉ, `growthos/worker.py`, `engine/assembler.py`, `engine/story_compile.py`, `supabase/migrations/20261003120000_*.sql`]
`growthos-worker.yml` → `worker.process_one` → `repo.claim_queued_item` → `assembler.run_for_content_item` :
1. `normalize_script` + `validate_script`, puis **modération avant le crédit** (`moderation.check_script/check_integrity`) ;
2. `repo.reserve_generation_credit` (RPC SQL atomique : verrou de l'organisation, plan `business` illimité, une retouche gratuite, **idempotent** via `credits_ledger`) ;
3. `_generate(...)` (TTS ElevenLabs par bloc, une image IA par bloc, Ken Burns FFmpeg) ;
4. **remboursement** (`refund_generation_credit`) si `_generate` ou `_publish_video` lève une exception ; `worker.process_one` marque ensuite l'item en échec et enregistre `generation_failed` ;
5. `versions.next_version_number` + `_publish_video` → fichier immuable `<id>/v<n>.mp4` ; rapport de coût, poster, miniature.
Sécurité de reprise : `repo.reclaim_stale_generating_items` (`_STALE_GENERATING_MINUTES = 15`). `story_compile.compile_story` existe mais **n'est pas branché** ; `MAX_RENDER_SHOTS = 12`.

## 3. Décision d'architecture
Un seul worker, un seul dépôt. Un nouveau package **`growthos/engine/story_animation/`** (contrat, chronologie, interface de rendu, contrôle qualité, rapport de coût) et un renderer **`rig_v1`** qui exécute le projet Godot du prototype dans un sous-processus. Aucun nouveau service. L'ancien chemin (`story.version` 1, Standard, Quiz) n'est pas modifié.
- Aiguillage unique dans `run_for_content_item`, **avant la réservation du crédit** : `story_animation.is_animated(data)`. Flag OFF ou contrat invalide ⇒ refus explicite, **rien n'est débité**.
- Les illustrations ne sont **pas générées au rendu** : elles viennent de « packs » préparés hors ligne (personnage, décors, accessoires). Le seul appel payant au rendu est la voix (ElevenLabs avec alignement), ce qui rend le coût marginal borné et prévisible.

## 4. Contrat d'animation versionné (`animation_schema_version: 1`)
Dans `content_items.script` (jsonb existant, **aucune migration SQL** pour le contrat) : `story.version: 2`, `story.animation_schema_version: 1`.
```
story: { version: 2, animation_schema_version: 1, language: "fr",
  characters: [{ id, name, voice_id, pack_id }],           // pack_id = identifiant d'un pack approuvé (catalogue serveur)
  shots: [{ id, setting_id, shot_type, camera: { move, zoom_from, zoom_to },
            speaker_id, dialogue,
            actors: [{ character_id, side, facing, mood, gaze, gesture_id, props: [prop_id] }],
            transition_in, intent }],
  music_id, budget: { max_usd, max_render_s, max_tts_chars } }
```
- **Catalogues fermés côté serveur** : `mood` (neutral, worry, angry, surprise, joy, puzzled, panic), `gesture_id` (accuse, defend, wring, indignant, clutch_head, point, hands_on_hips, idle…), `shot_type`, `camera.move`, `setting_id`, `prop_id`, `music_id`. L'IA propose, le serveur valide ; **aucun chemin, URL ni code ne vient de l'utilisateur ou de l'IA**.
- **Durées** : celles du contrat sont des estimations ; les durées finales viennent de l'audio mesuré. Le validateur actuel exige `somme des durées = target_duration_s` (`validator.py`) : en v2 ce contrôle devient « estimation à ±X % » et la chronologie finale est calculée au rendu. **[À décider en PR A]**
- **Plafonds** : ≤ 12 plans, ≤ 3 acteurs par plan, ≤ 60 s, ≤ 1 200 caractères de dialogue, ≤ 4 000 caractères de sous-titres, versions inconnues refusées, ajouts de champs optionnels = mineur, tout le reste = nouvelle version.
- **Miroir Python / TypeScript** avec fixtures communes, comme `test_validator_contract.py` (**[VÉRIFIÉ]** modèle existant).

## 5. Feature flag (OFF par défaut) et accès
- Worker : `STORY_ANIMATION_ENABLED=false` (variable du workflow, désactivée par défaut). Frontend : réutilise `STORY_GENERATION_ENABLED` (existant) + nouvelle option d'organisation, **admin plateforme uniquement** au départ.
- Flag évalué **avant** la réservation de crédit et **avant** tout appel externe. Un worker ancien qui rencontre un script v2 doit le refuser proprement (test de compatibilité).
- Interrupteur d'urgence : mettre le flag à OFF suffit ; les vidéos déjà publiées restent lisibles.

## 6. Flux du worker (pas à pas)
1. Valider le contrat v2 (catalogues, plafonds, packs autorisés pour ce compte).
2. Modération du texte (existante) ; `estimate()` sans effet de bord : caractères TTS, secondes de rendu estimées, coût USD estimé ⇒ refus si > `budget` ou plafonds.
3. `reserve_generation_credit` (inchangé).
4. TTS par réplique avec alignement (`tts.py` expose déjà `with-timestamps` **[VÉRIFIÉ]**), mesure des durées par `ffprobe`, classes de bouche, découpage des sous-titres, chronologie.
5. Rendu Godot en sous-processus : répertoire temporaire par job, délai maximal, aucune entrée réseau, texte utilisateur passé en **données JSON**, jamais interprété comme du code.
6. Contrôles qualité : durée vidéo = audio ±0,1 s, `blackdetect`, `freezedetect`, loudness, taille ≤ 40 Mo, résolution attendue ; échec ⇒ état de revue explicite (doctrine : « les problèmes de qualité non résolus exigent un état de revue »).
7. Mixage (voix, musique, SFX) puis `_publish_video` versionné (existant) ; `generation_cost_report` étendu (mesuré vs estimé, manquant ≠ zéro).
8. Toute exception après l'étape 3 ⇒ `refund_generation_credit` (existant). Crash ⇒ `reclaim_stale_generating_items` puis reprise idempotente.

## 7. Crédits et remboursements
- Réutiliser la RPC existante (1 crédit par run, une retouche gratuite, idempotence) : **aucune migration pour la bêta admin**. 
- **[DÉCISION]** prix en crédits d'une vidéo animée (1 crédit vs poids supérieur). Si > 1 : migration séparée (`p_cost`) avec tests SQL dans `supabase/tests/`, **jamais appliquée sans accord**.
- Tests de remboursement à chaque étape : modération, estimation, TTS, rendu (timeout), contrôle qualité, publication, crash du worker ⇒ exactement un remboursement, jamais deux débits.
- La migration en attente `supabase/pending/business_monthly_credit_quota.sql` **[VÉRIFIÉ présente, non analysée]** est à examiner avant de définir les quotas.

## 8. Quotas et plafonds
Par vidéo : plans, durée, caractères, taille, délai de rendu (≈ 10 min), budget USD. Par organisation : 1 rendu animé simultané, plafond quotidien, tentatives ≤ 3 (existant). Global : concurrence maximale de rendus, alerte quand la consommation ElevenLabs approche 80 % du quota mensuel du compte (à l'audit : 30 043 / 121 032 caractères utilisés, plan Creator). Tout dépassement ⇒ refus avant crédit.

## 9. Sécurité et isolation
Packs lus uniquement dans un dossier fixe par identifiant du catalogue (anti-traversée de chemin) ; stockage et chemins construits par le serveur avec préfixe de compte ; bucket `content-videos` privé **[VÉRIFIÉ le 2026-10-24]** + URL signées pour la lecture ; journaux sans dialogues complets ni URL signées ; secrets uniquement dans les secrets GitHub ; sous-titres échappés ; fichiers temporaires supprimés ; pas de téléchargement de ressources externes pendant le rendu ; limites CPU/mémoire/temps sur le sous-processus.

## 10. Plan de tests
Unitaires : validateur (Python + TypeScript, fixtures communes), classes de bouche, découpe des sous-titres, construction de chronologie, estimateur de coût. Intégration : worker avec TTS et Godot simulés — succès, flag OFF, plafonds, **remboursement à chaque étape**, reprise après crash, concurrence. Régression : suites Standard et Quiz inchangées, clips de référence comparés par `ffprobe`. Rendu doré : clip de 3 s sur le runner (durée, dimensions, pas d'image noire/gelée). Sécurité : chemins malveillants, JSON surdimensionné, injections dans les sous-titres, identifiants de pack d'un autre compte. E2E : **branche Supabase isolée**, jamais le projet partagé Preview/Production. CI : installer et mettre en cache Godot (leçon de la PR #72 : `ffmpeg` absent du runner l'avait fait échouer).

## 11. Déploiement et retour arrière
P0 contrat + validateurs seulement → P1 bibliothèque pure (chronologie, lip-sync, qualité) → P2 renderer en ligne de commande sur fixtures → P3 branche worker derrière flag (admin, branche Supabase) → P4 bêta fermée → P5 revue puis généralisation. Retour arrière : flag OFF ; aucune migration destructrice ; les anciens items ne sont pas touchés.

## 12. Découpage en PR (brouillons, aucune fusion automatique)
A. Contrat + validateurs Python/TS + fixtures. B. Bibliothèque chronologie/lip-sync/qualité (fonctions pures). C. Interface de rendu + projet Godot empaqueté + CLI locale. D. Aiguillage du worker derrière flag + tests de crédits. E. CI avec Godot + rendu doré. F. Interface frontend sous flag (aperçu par storyboard fixe, estimation affichée). G. Exploitation : surveillance, runbook, alertes.

## 13. Risques et décisions requises
| # | Sujet | Statut |
| --- | --- | --- |
| 1 | **Droits d'usage commercial** des images générées (OpenAI) et des voix (ElevenLabs) — conditions non lues | **bloquant avant toute diffusion** [DÉCISION] |
| 2 | Production des packs de personnages (génération IA retouchée vs illustrateur) | [DÉCISION] |
| 3 | Rendu Godot sur le runner Linux (installation, rendu logiciel, durée, minutes facturées) | [À VÉRIFIER] mesure en PR C/E |
| 4 | Prix en crédits d'une vidéo animée | [DÉCISION] |
| 5 | Niveau artistique : le prototype reste en deçà des références (marionnette) | accepté par l'utilisateur pour la bêta |
| 6 | Reprise des jobs bloqués pendant un rendu long (> 15 min) | [À VÉRIFIER] |

## 14. Ce que ce plan ne fait pas
Aucune modification du worker, du frontend, de la base ou des workflows ; aucune fusion ; aucune activation. La première PR de code (A) ne sera ouverte qu'après l'accord de l'utilisateur sur ce plan et sur les décisions 1 à 4.
