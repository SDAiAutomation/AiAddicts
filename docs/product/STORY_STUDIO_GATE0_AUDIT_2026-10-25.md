# Story Studio — Gate 0 : audit en lecture seule (2026-10-25)

Réponse au `FACELOOP_STORY_STUDIO_MASTER_BRIEF_CLAUDE.md` du 25 octobre 2026. **Aucun code modifié, aucune API payante appelée, aucun déploiement pendant cet audit.** Ce document remplace la liste de livrables du brief (§10) tant qu'il n'y a rien de plus à dire : le dépôt contient déjà 24 documents `docs/product/STORY_STUDIO_*.md` (analyse des références, plan Gate 4, runbook, état du 2026-10-25) ; je les référence au lieu de les dupliquer. Le chemin `docs/story-studio/` du brief n'existe pas ; je garde la convention existante `docs/product/`.

Légende : **EXISTANT** (lu dans le code et couvert par un test ou une exécution) · **PARTIEL** · **ABSENT** · **NON VÉRIFIÉ** (supposé, pas prouvé). « Fusionné » n'est jamais écrit pour « fonctionne en production ».

## 1. État factuel des dépôts (vérifié le 2026-10-25)

| Sujet | Fait | Preuve |
| --- | --- | --- |
| Backend `AiAddicts`, branche `growthos/mvp` | tête `44ac58d` (fusion de #88, 2026-10-24) | `git log origin/growthos/mvp` |
| Frontend `growthos-web`, branche `master` | tête `d45caf8` (fusion de #159, 2026-10-24) | `git log origin/master` |
| PR backend fusionnées | #71, #75, #85, #86, #87, #88 | `gh pr view` |
| PR backend **fermées sans fusion** | #73, #74, #76–#84 : leurs commits sont dans `growthos/mvp` via la fusion de #85 (ancêtres vérifiés avec `merge-base --is-ancestor`, y compris #75 rouverte et fusionnée) | gh + git |
| PR backend ouvertes, anciennes | #6, #45, #62, #63, #64, #72 (prototypes / hors sujet) : à trier, non touchées | `gh pr list` |
| PR frontend | #154, #156–#159 fusionnées ; #155 fermée (contenu inclus dans #156) | gh |
| Revue indépendante des PR fusionnées | **0 revue** sur #85–#88 et #156–#159 (commentaires automatiques seulement), alors que `AGENTS.md` prévoit une revue de Codex | `gh pr view --json reviews` |
| Branche de travail non fusionnée | `docs/story-studio-state-2026-10-25` (état, banc d'écriture, ce document) | git |
| Activation | variable de dépôt `STORY_ANIMATION_ENABLED=true` (2026-10-24 19:33) ; variable Vercel production `STORY_ANIMATION_ENABLED=1` ; accès réservé aux administrateurs plateforme (`ADMIN_USER_IDS` présent dans Vercel) | `gh variable list`, API Vercel |
| Exécutions du worker dédié | **une seule**, 2026-10-24 19:56, succès (« La pendule hypnotique »), **avant** les correctifs #86–#88 | `gh run list` |
| Vidéo réelle produite | 33,4 s, 1080×1920, voix + sous-titres, 5 scènes (ffprobe) | fichier téléchargé et mesuré |
| Bucket `story-packs` | privé, 0 politique, `prototype_v1` et `couleur_v1` (23 PNG + manifeste SHA-256 chacun) | SQL `storage.buckets`, `pg_policies` |
| Tests | paquet `story_animation` : 122 OK ; web `story-*` : 103 OK ; suite moteur complète : 3 erreurs **antérieures** (`test_explainer_generators`, `test_explainer_pipeline`, `test_thumbnail`), identiques sans mes changements | exécutions locales |

**À signaler.** (1) Les drapeaux sont déjà allumés en production pour les administrateurs : c'est le résultat d'ordres explicites de l'utilisateur le 2026-10-24 ; le brief demande de ne rien activer sans accord, donc je propose d'en décider à nouveau (§6, décision D1). (2) Des appels payants ont eu lieu avant ce brief, avec autorisation écrite : images OpenAI (≈ 0,60 $ estimé au total, journal `experiments/story_gate1/out/cost_ledger.json`), une génération ElevenLabs de test, et, à la fin de la session précédente, le banc d'écriture avec l'API texte d'OpenAI (≈ 200 000 jetons, terminé avant la réception du brief). **Plus aucun appel depuis.**

## 2. Matrice brief → réalité

### 2.1 Décisions produit fermes (§1 du brief)
| Exigence | Statut | Preuve / écart |
| --- | --- | --- |
| Durée ≥ 60 s, cibles 60/90/120/180/300 s, mesurée sur le fichier final | **ABSENT — bloquant** | `contract.py:29 MAX_DURATION_S = 60.0` (plafond, pas plancher) ; `timeline.py:40` et `rig_v1.py:57` refusent > 60 s ; aucun plancher. `MAX_SHOTS = 12`, `MAX_DIALOGUE_CHARS = 1200` (≈ 86 s de parole à 14 car/s), `MAX_SHOT_DIALOGUE_CHARS = 400`. La seule vidéo réelle fait 33 s. Mesure sur fichier final : **PARTIEL** (`quality.judge_media` compare durée image/son, pas la durée cible). |
| Genres généralistes | **PARTIEL** | idée libre en texte ; aucun champ genre/ton dans le contrat ni l'éditeur ; le prompt de proposition (`animated-proposal.ts`) est orienté comédie légère. |
| Réutiliser le moteur narratif Standard | **ABSENT pour Story Studio v2** | `animated-ai-actions.ts` appelle OpenAI avec son propre prompt (`gpt-5-mini` par défaut) ; il n'utilise ni `callOpenAiScript`, ni `planStory`, ni `retention`, ni `script-length`. Voir §3. |
| Godot comme moteur principal, FFmpeg | **EXISTANT** | `godot/rig_v1/scene.gd` (739 lignes), `rig_v1.py`, mix FFmpeg dans `voices.py`. Mesures : 51,5 s de rendu + 19 s d'encodage pour 21,6 s de vidéo sur `ubuntu-latest` (run 40115329358) ; ≈ 90 s sous Windows pour 33 s. |
| Images : assistance manuelle, pas d'API payante sans accord | **Violé avant le brief, avec accord écrit** ; **EXISTANT** côté produit : aucun appel OpenAI/Anthropic dans `engine/story_animation` hors modération (`moderation.py` : omni-moderation gratuite + Claude Haiku) | grep |
| Budget zéro / pas de TTS payant en test | **PARTIEL** | TTS = ElevenLabs uniquement (`engine/tts.py`), 0,18 $/1000 car. estimé dans le workflow (0,3 par défaut du code). **Aucun TTS local** (`espeak`, `flite`, `piper` absents de ce poste). Audio existant réutilisable : `experiments/story_gate1/out/audio/*.mp3|wav` (histoire du Gate 3 uniquement). |
| Aucune production sans accord ; isolation tenant, RLS, secrets, remboursements | **PARTIEL** | remboursement exactement une fois et refus avant crédit : testés (`test_pipeline.py`, `test_story_animation_routing.py`) ; RLS `content_items` héritée ; flags + administrateur plateforme (`animated-actions.ts`) ; bucket privé sans politique. Voir §4 pour les réserves. |
| Aucun GO commercial sans vidéo entière, art approuvé, droits | **NON ATTEINT** | aucune vidéo ≥ 60 s ; art non validé par un humain ; droits des images et des voix **non vérifiés**. |

### 2.2 Éditorial (§2, §3, §7)
| Exigence | Statut | Preuve / écart |
| --- | --- | --- |
| Mode Libre | **PARTIEL** | idée + scènes saisies à la main + proposition IA (`animated-ai-actions.ts`). |
| Mode Assisté (question, auteur, œuvre, théorie → angles vérifiables → synopsis) | **ABSENT** | aucune recherche documentaire, aucun angle proposé. |
| Recherche documentaire, provenance, vérification | **ABSENT pour Story Studio**, **PARTIEL ailleurs** | Standard : `invented-claims.ts` (détecteur consultatif de faux témoignages), `quiz-verification` + `verifyQuizAnswers` (gpt-5). Explainer (`engine/explainer/schema.py`) : une affirmation chiffrée sans `source` est refusée ; `critic.py` juge la vérité de la narration. Rien de tout cela n'est branché sur Story Studio. |
| Distinguer fait / interprétation / hypothèse / fiction | **ABSENT** | le contrat v2 n'a aucun champ `nature`, `sources`, `provenance`. |
| Structure narrative (hook, enjeu, tournant, résolution) | **PARTIEL** | le moteur Standard a STOP→HOLD→PROGRESS→REWARD→RETURN (`engine/retention.py`, 1383 lignes, déterministe, sans appel IA) ; Story Studio ne l'applique pas. |
| Qualité d'écriture mesurable | **NON VÉRIFIÉ** | banc local (`experiments/story_writing/bench.py`, **11 concepts sur 12 jugés** : le processus s'est arrêté avant le douzième, cause non examinée) : l'écriture en plusieurs passes bat la production actuelle dans 22 jugements sur 22 ; le même prompt sur un modèle plus fort bat la production dans 22 sur 22 ; l'écriture en passes bat ce dernier dans 17 jugements sur 22. Juge = modèle, **ce n'est pas un public**. Résultats dans `~/story_studio_work/bench1/bench.json` (hors dépôt), à présenter à l'utilisateur. |

### 2.3 Architecture (§4)
| Brique | Statut | Preuve / écart |
| --- | --- | --- |
| Contrat de scène versionné | **EXISTANT** (`story.version 2`, `animation_schema_version 1`, 43 cas partagés Python/TS) | `contract.py`, `animation-contract.ts`, `fixtures/animation_contract.json`. |
| Champs du contrat demandés mais absents | **ABSENT** | état émotionnel avant/après, axes de regard, continuité des accessoires, exigences de sous-titres, provenance de l'idée, rôle de narrateur. Présents : id, locuteur, texte, décor, plan, caméra, acteurs (côté, orientation, humeur, geste, accessoires), transition, intention, budget. |
| Voix off + dialogues combinables | **ABSENT** | chaque réplique est portée par un personnage du rig (`pipeline.py`), pas de narrateur sans corps. |
| Story Adapter (récit Standard → scènes) | **ABSENT** | l'ancien `story_compile.py` fait l'inverse (storyboard v1 → blocs Standard), « pas branché » par son propre en-tête. |
| Contrôle de continuité | **ABSENT** | seuls les catalogues fermés sont validés ; pas de vérification d'apparence, d'objets, de lumière. |
| Bibliothèque d'assets versionnée | **PARTIEL** | packs avec manifeste SHA-256 et `version` entier ; pas de licence/provenance, pas de bible visuelle. |
| Lip-sync, sous-titres, mixage | **EXISTANT** (`lipsync.py`, `subtitles.py`, `voices.py`) | qualité réelle du lip-sync **NON VÉRIFIÉE** (3 classes de bouche c/o/r, pilotées par l'enveloppe audio ; le rendu local de test utilisait un motif synthétique). |
| Validation technique du rendu | **PARTIEL** | `quality.judge_media` : durées, résolution, fréquence d'images, taille, plans noirs/figés, saturation audio. Aucune validation éditoriale, scientifique ou de continuité. |
| Worker dédié, packs privés, workflow manuel | **EXISTANT** | `animation_worker.py`, `story-animation-worker.yml` (manuel, ignoré sans variable), `pack_fetch.py`. |

### 2.4 Qualité graphique (§6)
| Exigence | Statut | Preuve / écart |
| --- | --- | --- |
| Un seul style réussi d'abord | **ÉCART DE PORTÉE** | quatre looks ont été ajoutés (noir, sépia, cyanotype, couleur) avant la validation d'un seul ; le brief demande l'inverse. À figer : un look « officiel » (noir 1930) en attendant validation. |
| Bible visuelle (model sheets, palette, proportions, visèmes, règles) | **ABSENT** | |
| Assets : PNG par pièce, nommage, pivots, manifests, checksum, licence | **PARTIEL** | 23 PNG nommés, ancres en dur dans `scene.gd` (`CH`), SHA-256 ; pas de licence ni provenance. |
| Gestes et idle | **PARTIEL** | 11 gestes (`idle … run_away`), respiration, nods, dérive des mains (PR #86). Absent : marcher dans la scène hors `run_away`, se tourner, prendre/donner un objet, rire, pleurer, hésiter. |
| Défauts à éviter (mains sur la bouche, immobilité…) | **PARTIEL** | `point` corrigé et gardé par `test_gesture_clearance.py` ; `clutch_head` couvre l'œil de Pip (voulu mais à juger) ; reste de l'espace de poses × plans non exhaustivement vérifié. |
| Benchmark d'autres moteurs | **ABSENT** | non nécessaire tant qu'un défaut Godot n'est pas prouvé. |
| Droits des images générées | **NON VÉRIFIÉ — bloquant commercial** | sprites et décors venant de l'API OpenAI Images ; conditions à relire avant diffusion. |

## 3. Écart central : Story Studio ne réutilise pas le moteur Standard
Ce que Standard possède déjà (à réutiliser, pas à recopier) :
- **Génération de script** : `growthos-web/src/app/(app)/content/ai-actions.ts` — `buildManualSystemPrompt`, `callOpenAiScript` (validation + relance), `planStory` (plan promesse / indices / révélation / fin, **derrière `SCRIPT_TWO_STEP=1`, variable absente de Vercel production**), `strategy-brief`, `narrative-perspective`, `niche-narrative`.
- **Cibles de durée** : `src/lib/script-length.ts` — TikTok 62–74 s, YouTube 60–120 s, débit mesuré (fr 213 mots/min), bornes dures 58–80 s.
- **Diagnostics de rétention** (déterministes, 0 €) : `engine/retention.py`, `editorial_quality.py`, `series-editorial-score.ts`, `scene-variety.ts`, `invented-claims.ts`, `originality.py`.
- **Vérité** : `engine/explainer/critic.py` et `schema.py` (affirmations avec source).
Ce que Story Studio fait à la place : un seul appel `gpt-5-mini`, 5 scènes de ≤ 400 caractères, aucune cible de durée, aucun diagnostic de rétention.

## 4. Sécurité, coûts, risques
- **Sécurité (positif)** : bucket `story-packs` privé et sans politique (lecture par rôle de service uniquement) ; sorties du modèle réduites aux catalogues fermés (`sanitizeProposedShots`, `parse_*`) ; refus avant tout crédit ; remboursement idempotent ; modération avant dépense ; accès limité aux administrateurs plateforme.
- **Réserves** : (a) le workflow dédié donne au job des secrets de production (service role Supabase, ElevenLabs, OpenAI, Anthropic) ; seuls OpenAI (modération) et Anthropic (Haiku) sont utiles à la modération, le moindre privilège n'a pas été revu par un humain ; (b) aucun des PR #85–#88 / #156–#159 n'a eu de revue indépendante ; (c) le changement #85 touche le chemin du worker principal (`repo.claim_queued_item`, un test ajouté, mais pas de test de bout en bout Standard/Quiz exécuté ici) ; (d) un rendu Linux avec le pack couleur n'a pas été mesuré ; (e) code mort : ancien Story Studio v1 (`story-studio/actions.ts`, `ai-actions.ts`, `storyboard.ts`, `render.ts`) et variable Vercel `STORY_GENERATION_ENABLED=1` inutilisée.
- **Coûts mesurés ou estimés** : TTS ≈ 0,22 $ pour 1260 caractères (≈ 90 s) à 0,18 $/1000 car. ; rendu : ratio mesuré 2,4 à 2,7× la durée (estimation du code : 4×) donc ≈ 4 à 6 min pour 90 s, 13 à 20 min pour 300 s, sous le délai de 30 min du workflow dédié ; stockage : packs ≈ 15 Mio chacun ; modération : Claude Haiku par vidéo (non mesuré). **Coût externe cible 0 € : atteignable seulement avec un TTS local ou de l'audio déjà généré** (§5, P3).

## 5. Plan priorisé minimal et critères GO / NO-GO
Principe : ne rien refaire de ce qui existe ; chaque étape se termine par une décision.

| Priorité | Étape | Contenu | Coût | GO si | NO-GO si |
| --- | --- | --- | --- | --- | --- |
| P0 | **Gate 1 — trois scénarios de 90 s** | psychologie sociale (la foule), émotion (la petite générosité), idée d'auteur (Orwell, fiction explicitement signalée) ; sources, statut fait/interprétation/fiction, estimation audio (≈ 1260 caractères), plan de scènes. Recherche web gratuite uniquement. | 0 € | validés par l'utilisateur ; aucune citation non sourcée | une source ne se vérifie pas |
| P1 | **Contrat v2.1 (schéma versionné)** | plancher et plafond de durée par cible (60–300 s), limites de scènes et de caractères relevées en proportion, champs `genre`, `nature`, `sources`, rôle `narrator` ; v2.0 reste valide ; cas partagés Python/TS mis à jour | 0 € | 122 + 103 tests existants verts + nouveaux ; Standard et Quiz inchangés | une régression sur Standard/Quiz |
| P2 | **Adaptateur Standard → scènes** | réutiliser `planStory`, `script-length`, `retention`, `invented-claims` (appel unique, sans nouveau moteur) ; mêmes validations côté Story Studio | 0 € en tests (fixtures), tokens OpenAI seulement à l'usage | un script Standard de 60–90 s devient un contrat valide sans perdre sa structure | duplication de logique narrative |
| P3 | **Audio local gratuit** | adaptateur `Ports.synthesize` pour un TTS local (candidat : Piper, à vérifier : licence commerciale des voix françaises, qualité) ou audio préexistant ; **pas d'ElevenLabs en test** | 0 € | voix intelligible, licence commerciale confirmée | licence incompatible → rester sur fixtures audio et arrêter avant P5 |
| P4 | **Gate 3 — personnages** | bible visuelle (model sheets, palette, expressions), corrections de rig (marcher, se tourner, objets), extrait local de 8–12 s ; références **manuelles** par l'utilisateur via ChatGPT ; pas d'API images | 0 € externe | extrait approuvé visuellement par l'utilisateur | gestes qui cachent la bouche ou membres qui traversent le corps |
| P5 | **Gate 4 — histoire entière ≥ 60 s** | rendu local, ffprobe ≥ 60 s, MP4, captures, logs de temps et d'usage, coût externe 0 € | 0 € | durée mesurée dans la tolérance, audio sans coupure, sous-titres sans débordement, validation humaine | durée < 60 s, ou tests verts mais qualité refusée |
| P6 | **Gate 5 — durcissement et décision** | revue de sécurité (moindre privilège du workflow), droits des assets, rendu Linux avec les deux packs, non-régression Standard/Quiz complète | 0 € | tous les points ci-dessus + accord écrit | droits non vérifiés → pas d'activation publique |

## 6. Décisions demandées à l'utilisateur
- **D1.** Éteindre `STORY_ANIMATION_ENABLED` (GitHub + Vercel) jusqu'à Gate 5, ou le laisser actif pour les administrateurs ? Recommandation : l'éteindre, le brief interdit les activations sans accord et aucune vidéo ≥ 60 s n'existe.
- **D2.** Accepter le contrat v2.1 (P1) : plafonds relevés, champs de provenance, narrateur.
- **D3.** TTS local : autoriser l'essai de Piper (téléchargement d'un binaire et de voix, licences à vérifier) ou ne tester qu'avec de l'audio déjà généré.
- **D4.** Figer **un seul** look officiel (noir et blanc 1930) jusqu'à validation artistique, et geler les trois autres.
- **D5.** Fusionner ou non la branche `docs/story-studio-state-2026-10-25` (état, banc d'écriture, cet audit).
- **D6.** Trier les anciennes PR ouvertes #6, #45, #62, #63, #64, #72.

## 7. Ce que cet audit ne prouve pas
Qualité artistique, lip-sync réel sur audio réel, rendu Linux avec le pack couleur, parcours connecté complet, mode sombre de l'éditeur, non-régression bout en bout de Standard et Quiz, droits d'usage des assets, rétention d'audience. Aucun de ces points n'est déclaré acquis.
