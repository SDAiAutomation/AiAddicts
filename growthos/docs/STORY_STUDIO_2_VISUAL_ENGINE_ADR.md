# ADR — Story Studio 2.0 : moteur de récit illustré

> Statut : proposition + fondation hors ligne implémentée (2026-10-30). Rien n'est branché sur le worker, aucun drapeau activé,
> **aucun appel payant n'a été fait**. Les coûts ci-dessous sont des **estimations non chiffrées** (aucun tarif n'est configuré dans cette session).
> À lire avec `PRODUCT_DOCTRINE.md` et, côté web, `docs/product/STORY_STUDIO_2.md` / `STORY_STUDIO_VISION.md`.

## 1. Audit (Phase 0) — ce qui existe réellement

| Sujet | Constat (fichier) |
|---|---|
| Story Studio actuel | Deux chemins : (a) **animé** (`engine/story_animation/`, schéma 2, rig + Godot, GO interne / NO-GO public) ; (b) `engine/story_compile.py` : un storyboard `content_format: "story"` -> blocs Standard, « pas encore branché dans `script.normalize_script` ». `story_adapter.py` pose « Story Studio n'a pas de moteur narratif propre ». |
| Images OpenAI | `openai_images.generate_image/edit_image` (clé serveur, retry/backoff, 13 s entre appels, classification d'erreur, usage réel via `pop_last_usage`). `image_model_router.select_model(preview|final|edit)`. `image_prompt_builder`, `image_character_bible` (fiche **textuelle** conditionnelle), `image_style_bible`, `image_quality_control` (QC vision optionnelle). |
| Cohérence personnage | Les images de référence (`/edits`) ont été **testées et abandonnées** : elles figent la pose (`image_character_bible.py`, `visuals.py`). Aucun test visuel de cohérence n'existe. |
| Cache | `asset_store` (Supabase, clés `make_key`) + `generation_cache.fingerprint` (script + code + env). |
| Voix | `tts.synthesize_with_timestamps` (ElevenLabs, timings de mots), `assembler.block_voice_id` (voix par bloc). |
| Rendu | `video.render_final` : un clip Ken Burns par plan, fondu au noir optionnel, sous-titres ASS, H.264/AAC `+faststart`. **Pas de fondu enchaîné.** |
| Coûts | `assembler._generation_cost_report` : voix, script, images ; tarifs lus dans l'environnement. |
| Tests | ~1 350 tests `unittest` (`growthos/tests`) + `story_animation` (202) + `story_intelligence` (42). |

### Dette / risques relevés (preuves)
1. **`image_model_router.estimate_cost` renvoie 0 $ pour le modèle par défaut** (« facturé au token, reste à 0 ») : un budget fondé dessus serait silencieusement faux. -> `story_visual.cost` échoue **fermé** (`unpriced`).
2. `generate_image` n'expose pas de graine ni de contrôle de style hors prompt ; la cohérence repose sur le texte.
3. Trois échecs préexistants dans `tests/` sur `growthos/mvp` (`test_explainer_generators`, `test_explainer_pipeline` : import ; `test_graph_voice_sync…identical_to_the_unstaged_scene` : comparaison d'octets), **identiques avec et sans ce changement**.
4. Mise en production d'un 4ᵉ format = nouveau chemin dans `assembler.run_for_content_item` + éventuelle migration (`content_format`) : **non fait, à décider**.

## 2. Décisions

1. **Un paquet isolé** `engine/story_visual/` (zéro modification de code existant) au-dessus des services partagés ; les modules existants sont **appelés**, pas copiés : `image_prompt_builder`, `image_character_bible`, `image_model_router`, `openai_images` (via `orchestrator.openai_provider`), `asset_store.make_key`.
2. **Contrat unique `story_plan` v1** (`schema.py`) ; quatre stratégies narratives (`formats.py`) sur un seul rendu ; provenance et factualité validées (faits sourcés, citations, fiction jamais présentée comme fait, URL de sources publiques https — jamais téléchargées).
3. **Direction visuelle avant l'image** : chaque scène porte comprendre / ressentir / métaphore / essentiel / omettre / continuité ; trois directions artistiques réutilisables (`art_directions.py`).
4. **Typographie locale** (`overlay.py`, Pillow, Poppins-Bold du dépôt) : jamais dans l'image IA ; corps ≥ 64 px, contraste mesuré ≥ 4,5, zone sûre Shorts.
5. **Voix d'abord** (`timing.py`) : durées de scène = audio mesuré + pause ; aucun recouvrement ; maintien final ≥ 3 s ; transitions confinées à la pause.
6. **Budget fail-closed** (`cost.py`) : plafond 2,00 $ (cible 1,50 $), configurable ; `BudgetTracker.reserve` refuse **avant** l'appel payant ; coût inconnu = refus.
7. **Références d'image : désactivées par défaut** (`reference_policy`) ; autorisées seulement si le coût d'édition est connu et si un personnage revient après ≥ 3 scènes d'absence. À valider par test visuel payant.
8. **Reprise et idempotence** (`orchestrator.py`) : manifeste par (locataire, histoire), cache par clé déterministe liée au locataire, régénération d'une seule scène.
9. Rendu FFmpeg en **argv** (pas de shell), 1080×1920, H.264 yuv420p, AAC, cut / fondu enchaîné / fondu par le noir, reframing optionnel ≤ 5 %.

## 3. Livré dans cette PR / pas livré

| Livré (testé, hors ligne) | Non livré |
|---|---|
| Contrat + validation, provenance, anti-SSRF, 4 stratégies, prompt planificateur + parseur non fiable | **Appel LLM du planificateur** (prompt et parseur prêts ; branchement = appel payant à autoriser) |
| 3 directions artistiques, compilateur de prompt, continuité testée sur le texte | **Cohérence visuelle réelle** : jamais mesurée |
| Estimateur, budget, suivi de dépense, cache, orchestrateur, reprise | Câblage worker / `assembler` / file de jobs / migration |
| Calage voix, SRT, typographie, rendu MP4 réel (2 récits d'exemple, coût 0) | **Voix ElevenLabs réelle** (le calage reçoit des durées mesurées ; `tts.synthesize_with_timestamps` à brancher) ; **recherche** (les sources sont fournies, non collectées) |
| | Interface web de création (voir PR frontend : contrat miroir seulement) |

## 4. Coûts — estimé vs mesuré

- **Mesuré** : 0 $ (exemples rendus avec des illustrations de substitution et une voix sinusoïdale).
- **Estimé** : non chiffrable honnêtement ici (aucun tarif configuré). Formule : `images × STORY_IMAGE_USD_EACH + (caractères/1000) × ELEVENLABS_USD_PER_1K_CHARS + script + stockage`. Pour 8 scènes, le plafond de 2 $ impose `coût_image ≤ (2 − voix − script − stockage) / 8` ; la cible de 1,50 $ est plus serrée. Mesurer le coût d'une image réelle (usage renvoyé par l'API) est le **premier objectif du pilote**.

## 5. Plan de pilote payant (non exécuté — approbation requise)
1. Renseigner les tarifs (`STORY_IMAGE_USD_EACH` mesuré sur 1 image, `ELEVENLABS_USD_PER_1K_CHARS`, `SCRIPT_PRICE_*`) ; `estimate_episode` doit afficher `unpriced: []`.
2. Un épisode factuel + une fable, 8 scènes, `STORY_BUDGET_USD=2`, compte de test, drapeau local uniquement.
3. Mesurer : coût réel par poste (`BudgetTracker.spent`), cohérence personnage (revue humaine des scènes avec Rowan), lisibilité mobile, désynchronisations, taille MP4.
4. Décider : références d'image oui/non, qualité d'image par scène, durée par défaut.

## 6. Paquet de revue indépendante (Codex)
- **Architecture** : paquet isolé, aucune modification de module existant ; vérifier la réutilisation (pas de second constructeur de prompt).
- **Sécurité** : entrées modèle/recherche non fiables (`parse_plan_response`) ; anti-SSRF (`is_safe_source_url`) ; identifiants/chemins (`cache.py`, `orchestrator._manifest_path`) ; FFmpeg sans shell ; aucune clé hors `openai_images`. **À revoir** : quotas/limites de débit par locataire (non implémentés ici : relèvent du worker).
- **Régressions** : suites existantes inchangées (voir §1 point 3) ; ce paquet n'est importé par aucun module.
- **Risques de coût** : tarifs inconnus ; boucle QC (`image_quality_control`) non utilisée ici ; régénérations manuelles à plafonner par épisode.
- **Qualité visuelle** : non jugée (illustrations de substitution) ; typographie mesurée (contraste, taille), pas la direction artistique.
- **Dette** : `estimate_cost` à 0 $ (point 1) ; deux chemins « story » à unifier ; sources d'exemple à vérifier (voir `sample.py`).
- **Déploiement** : non prêt ; prérequis : câblage derrière drapeau, migration éventuelle, pilote payant approuvé.
