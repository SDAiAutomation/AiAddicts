# Story Studio 2.0 — contrat d'API, rapport de revue et préparation du pilote payant

> 2026-10-30. Aucun appel payant n'a été fait. Drapeau `STORY_VISUAL_ENABLED` éteint par défaut. Complète
> `STORY_STUDIO_2_VISUAL_ENGINE_ADR.md`.

## 1. Ce qui est branché (derrière drapeau éteint)
`assembler.run_for_content_item` appelle `story_visual.contract.route_for(script)` : « legacy » pour tout script qui n'a pas
`content_format: "story_visual"` (Standard, Quiz, Story animé : comportement inchangé, test de non-régression), « visual » seulement si
`STORY_VISUAL_ENABLED=1`, sinon `VisualDisabled` **avant** crédit ou appel fournisseur. `_run_visual` branche les services réels dans
`story_visual.pipeline.run` (ports injectés) : administrateur plateforme seulement (comme l'animé), modération existante, crédit
réservé puis remboursé en cas d'échec, OpenAI Images (`openai_provider`), ElevenLabs (`tts.synthesize_with_timestamps`), publication
via `_publish_video`/versions. Le planificateur LLM (`planner.openai_chat_provider`) n'est **pas** appelé par le worker : l'écriture du
plan est une étape d'API distincte (futur écran), le worker reçoit un plan déjà validé.

## 2. Contrat d'API (miroir TypeScript : `growthos-web/src/lib/story-studio/visual-api.ts`, parité testée)
Le `tenant_id` vient de la session, jamais du corps (champs inconnus refusés).

| Opération | Entrée | Sortie |
|---|---|---|
| `plan` POST | `{idea, story_type, language?, target_duration_s?, art_direction?, voice_id?, sources?}` | `{plan, estimate}` — le serveur impose id, type, langue, durée, direction, voix et **sources** (le modèle ne peut citer que les sources fournies) |
| `estimate` POST | `{plan}` | `{estimate{estimated:true, complete, lines, unpriced}, decision{status ok/over_preferred/over_budget/unpriced, allowed}}` |
| `edit_scene` PATCH | `{scene_id, <champs éditables>}` | `{plan, invalidated{image, voice}}` — seul ce qui dépend du champ modifié est régénéré |
| `replace` PUT | `{scene_id, scene}` | `{plan, invalidated}` |
| `regenerate` POST | `{scene_id}` | `{job}` — plafonné (2 par scène, 6 par histoire par défaut) |
| `generate` POST | `{plan}` | `{job}` — idempotent (empreinte du plan), un seul exécuteur par histoire (verrou) |
| `status` GET | job | `{state, digest, progress, scenes[{image, voice, image_generations}], cost{estimated_usd, estimated:true, spent_usd, spent_by_kind, complete}, error, retryable, disclosure}` |

Codes d'erreur : `invalid_request, invalid_plan, unknown_scene, budget_refused, quota_exceeded, regeneration_limit, disabled, forbidden, not_found`.
`spent_by_kind` sépare `measured` / `estimated` / `unpriced` / `cache` ; `complete: false` = au moins un appel dont le coût est inconnu :
le total est alors **sous-évalué** et ne doit pas être affiché comme un coût.

## 3. Problèmes identifiés et corrigés (revue indépendante `engine-reviewer`, puis relecture)
| # | Gravité | Problème | Correction |
|---|---|---|---|
| 1-2 | Bloquant | Coût image inconnu enregistré comme 0 $ ; estimation enregistrée comme dépense réelle | `image_model_router.estimate_cost_or_none` / `is_priced` (additif ; `estimate_cost` inchangé, 0.0 = « non chiffré »), nature de chaque montant (`measured/estimated/unpriced/cache`) |
| 3 | Bloquant | Plan non revalidé : un `scene.id` hostile devenait un chemin | `generate_scene_images` et `synthesize_story` revalident le plan (échec fermé) |
| 4-5 | Important | `STORY_BUDGET_USD=0` -> 2 $ ; NaN/négatif acceptés par `reserve` | budget 0 respecté, valeurs non finies refusées, cible ≤ plafond |
| 6-7 | Important | Réservation non atomique ; budget remis à zéro à chaque relance | retenues atomiques ; dépense relue du manifeste (relancer ou régénérer ne réinitialise rien) |
| 8 | Important | Manifeste corrompu = tout repayer ; écriture non atomique ; pas de verrou | `ManifestCorrupt`, écriture atomique, verrou de job (`JobBusy`) |
| 9-10 | Important | Exception fournisseur non rattrapée ; échec sans borne ; chemin retourné non contrôlé | échec enregistré (coût inconnu), `needs_review` après 3 essais, chemin et image vérifiés |
| 11-12 | Important | `TypeError` sur entrée hostile ; champs de prompt non bornés | validation sans exception, champs ≤ 300 caractères |
| 13 | Important | Idée/sources pouvaient fermer leur balise de données | neutralisation des chevrons, sources non sûres exclues |
| 14-16 | Important | Chemins FFmpeg non gardés, pas de timeout, image sans limite de pixels | chemins absolus existants, timeout, limite 36 Mpx et formats, police du dépôt obligatoire |
| 17 | Important | Lisibilité mesurée mais non imposée | pire cas par cellule, `ok`, `needs_review` dans le résultat, mot géant coupé |
| 18 | Important | Estimation d'images sur prompts uniques | une image par scène ; `complete` signale un total partiel |
| 19 | Important | Parité TypeScript non couverte pour l'hostile | 17 cas hostiles/URL/voix ajoutés ; miroir aligné |
| 20-22, 25 | Mineur | cache non atomique/symlink ; URL `localhost.`/hex ; pause < transition ; transition inconnue | corrigés |
| 23-24 | Mineur | dérive audio/vidéo | tolérance de test resserrée à 0,15 s |
| 26 | Mineur | tests trop faibles | 28 tests de correctifs + cas de coût réel > attendu, NaN, 0 $, exception |
| 27 | Mineur | workflow CI dans la même PR | conservé (il ne teste que ce paquet) ; à scinder si vous préférez |

### Revues complémentaires (parité TS/Python, contrôle visuel du MP4)
| Source | Constat | Suite |
|---|---|---|
| `contract-parity` | 21 entrées où moteur et miroir web divergeaient (longueur UTF-16 vs points de code, `strip()` vs `trim()`, booléen pris pour entier, entier géant, `60.0`, voix non textuelle, conteneur vide, URL : IDN, `%`, antislash, port, clés de prototype `constructor`/`__proto__`, comparaison avant/après, arrondi du coût, `replace_scene` absent) | corrigés des deux côtés (URL jugée sur la chaîne brute par la même expression, `cpLen`/`pyStrip`, `Object.hasOwn`, comparaison canonique, arrondi par ligne, `replaceScene`) ; 40 cas de parité ajoutés + fixture de coût partagée |
| `render-checker` (MP4 d'exemple, illustrations et voix de substitution) | **légendes superposées pendant les fondus** ; deux plans de ~7 s sans mouvement ; texte trop bas/à droite (zone sûre Shorts) ; 3 s de silence final | texte désormais dans un **calque séparé à fondu séquencé** (`render.text_windows`, testé) ; caméra par défaut selon la direction artistique ; marges 96 px gauche / 168 px droite / 440 px bas ; maintien final 2,0 s |
| `render-checker` | coupe sèche et « flash » au fondu par le noir | **voulus** : transition `cut` du plan 1 et `fade` = fondu par le noir de 0,3 s ; non modifiés |
| non mesuré | déterminisme octet par octet du MP4 ; zone sûre officielle des Shorts (gabarit usuel utilisé) | à vérifier au pilote |

## 4. Prérequis du pilote payant (à cocher avant toute génération réelle)
1. **Autorisation explicite** du propriétaire pour les appels OpenAI Images, texte et ElevenLabs.
2. **Tarifs** : `STORY_IMAGE_USD_EACH` (mesuré sur 1 image réelle) ou `IMAGE_PRICE_IMAGE_OUT_PER_M` + `STORY_IMAGE_OUTPUT_TOKENS`, `ELEVENLABS_USD_PER_1K_CHARS`, `SCRIPT_PRICE_IN/OUT_PER_M` + `STORY_PLAN_TOKENS_IN/OUT`, `STORY_RENDER_USD`, `STORY_STORAGE_USD`. `estimate_episode` doit afficher `unpriced: []`.
3. `STORY_BUDGET_USD=2` (ou moins), `STORY_PLANNER_MODEL`, `STORY_DEFAULT_VOICE_ID` ou `voice_id` dans le plan.
4. **Base de données** : vérifier que `content_items.content_format` accepte `story_visual` (contrainte CHECK éventuelle) — migration additive à rédiger puis à faire appliquer par un humain si besoin ; non vérifié ici (aucune base consultée).
5. **Quota partagé entre workers** : aujourd'hui le quota réel est la réservation de crédit ; le verrou de job est local à un disque (un worker). Un second worker ou un disque éphémère (GitHub Actions) ne partage ni verrou, ni manifestes, ni cache : acceptable pour un pilote d'**un** épisode, pas pour de la concurrence.
6. **Persistance** : le répertoire de travail est éphémère sur le worker Actions ; la reprise après échec entre deux exécutions suppose un stockage (`asset_store`) non branché ici.
7. **Compte administrateur** (`ADMIN_USER_IDS`) et `STORY_VISUAL_ENABLED=1` **sur un environnement de test uniquement** ; retirer ensuite.
8. **Vérification humaine** des sources du récit factuel, du rendu (cohérence personnage, lisibilité mobile), et du jugement artistique.
9. `render-checker` et `contract-parity` sur le MP4 et les fixtures (non lancés dans cette session).

## 5. Recommandation GO / NO-GO pour la génération réelle
- **NO-GO public / production.**
- **GO conditionnel pour UN pilote interne** (un épisode, compte administrateur, environnement de test), **dès que** les prérequis 1 à 4 et 7 sont remplis et que vous avez approuvé le plafond de dépense. Les risques inconnus à mesurer : coût réel par image et par épisode, cohérence réelle des personnages, qualité de la voix et du calage, temps de rendu sur le worker.
