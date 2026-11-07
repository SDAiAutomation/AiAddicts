# Story Visual — dossier de préparation du pilote payant (un épisode interne)

> 2026-11-01. **Document de préparation : rien n'est lancé, aucun appel payant n'a été fait, aucun drapeau n'est activé, aucun tarif ni crédit
> n'est modifié.** Lancer le pilote exige l'autorisation explicite du propriétaire (liste exacte en §8).

## 1. Objectif et périmètre
Produire **un seul épisode** de ~60 s (récit illustré : 8 images, voix, texte animé, mouvement de caméra), sur l'environnement de **test**, avec un
compte administrateur de la plateforme, pour mesurer : le coût réel, la cohérence du personnage, la lisibilité mobile, la synchronisation voix/image et
la qualité perçue. Ce n'est pas une animation de personnages et ne doit jamais être présenté comme telle.

Hors périmètre : planificateur LLM (le plan est fourni : récit d'exemple du moteur), recherche, génération en production, exposition aux utilisateurs.

## 2. Ce qui est déjà en place (fusionné, drapeaux éteints)
Moteur `story_visual` (#103), ordre des gardes (#105), robustesse (#106 : arrêt après échec, cache persistant `asset_store`, quota partagé, **registre
durable de dépense** par épisode), contrats web (#175), parcours en simulation (#180, #181). Le worker refuse tout récit illustré tant que
`STORY_VISUAL_ENABLED` n'est pas activé, avant tout crédit ou fournisseur.

Ordre des gardes à l'exécution : drapeau → administrateur plateforme → plan valide → tarifs/budget → modération → quota partagé → registre de dépense →
**réservation de crédit** → fournisseurs ; avant **chaque** appel payant : plafond cumulé de l'épisode (registre durable), puis arrêt à la première
scène en échec.

## 3. Budget (estimation ≠ facture)
Seule donnée **mesurée** : 7 images `gpt-image-2.5-flare` qualité `low` 1024×1536 = **0,0643 $** (≈ 0,0092 $ l'image). Le tarif de la voix n'est **pas**
configuré ; 0,30 $ / 1 000 caractères est la valeur de repli de Standard (`assembler`), à remplacer par votre tarif réel.

| Poste | Hypothèse | Nominal | Au pire (+6 régénérations) |
|---|---|---|---|
| Images | 8 × 0,012 $ (mesuré 0,0092 + marge) | 0,096 $ | 0,168 $ |
| Voix | ~660 caractères × 0,30 $ / 1 000 | 0,198 $ | 0,198 $ |
| Planificateur | plan fourni, aucun appel (déclaré 0) | 0 | 0 |
| Rendu / stockage | exécuteur déjà payé / 0,01 $ | 0,01 $ | 0,01 $ |
| **Total** | | **≈ 0,30 $** | **≈ 0,38 $** |

Plafond recommandé du pilote : **`STORY_BUDGET_USD = 1,00 $`** (cible 0,50 $). Le registre durable refuse avant tout appel qui
ferait dépasser le cumul réservé de l'épisode, y compris en relance et en concurrence. Un coût réel supérieur à la retenue peut dépasser le plafond ; en concurrence, plusieurs appels déjà réservés peuvent présenter un dépassement.

## 4. Configuration du worker de TEST (aucune valeur de secret dans le dépôt)
| Variable | Valeur pour le pilote | Remarque |
|---|---|---|
| `STORY_VISUAL_ENABLED` | `1` **seulement** pendant le pilote, test uniquement | actif aussi avec `true`/`yes`/`on` ; à retirer ensuite |
| `ADMIN_USER_IDS` | identifiant(s) du compte administrateur de test | le moteur refuse tout autre appelant |
| `OPENAI_API_KEY`, `ELEVENLABS_API_KEY` | clés du fournisseur | **jamais** dans le dépôt, les tickets ou les journaux |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | base de **test** | |
| `IMAGE_MODEL_PREMIUM` / `IMAGE_FINAL_QUALITY` | `gpt-image-2.5-flare` / `low` | le coût n'a été mesuré que pour cette combinaison (sinon `OPENAI_IMAGE_QUALITY=medium` s'appliquerait) |
| `STORY_IMAGE_USD_EACH` | `0.012` | tarif d'une image, marge incluse |
| `ELEVENLABS_USD_PER_1K_CHARS` | **votre tarif réel** | inconnu : le moteur refuse sans |
| `STORY_RENDER_USD` / `STORY_STORAGE_USD` | `0` / `0.01` | |
| `SCRIPT_PRICE_IN_PER_M`, `SCRIPT_PRICE_OUT_PER_M`, `STORY_PLAN_TOKENS_IN`, `STORY_PLAN_TOKENS_OUT` | `0` | déclaration explicite : aucun appel au planificateur |
| `STORY_BUDGET_USD` / `STORY_BUDGET_PREFERRED_USD` | `1.00` / `0.50` | plafond cumulé de l'épisode |
| `STORY_VISUAL_MAX_JOBS_PER_DAY` | `1` | quota partagé par organisation |
| `STORY_DEFAULT_VOICE_ID` | identifiant ElevenLabs choisi | ou `voice_id` dans le plan |
| `STORY_VISUAL_UI_ENABLED` (site) | `1` sur l'environnement de test | l'interface reste réservée aux administrateurs |

## 5. Vérifications avant lancement (aucune ne dépense)
1. `python growthos/scripts/story_visual_pilot_preflight.py` sur le worker de test : **hors ligne**, n'affiche que « présente / absente » pour les secrets,
   donne PRÊT / NON PRÊT et la liste des points bloquants (testé : `tests/test_story_visual_pilot_preflight.py`). Sur l'environnement par défaut il répond NON PRÊT.
2. Requêtes SQL de lecture seule affichées par le script, à exécuter par un humain sur la base de test : contrainte `unique (content_item_id, kind, input_hash)`
   **et** `check (kind in ('voice','voice_words','image'))` de `content_assets` (le registre de dépense en dépend), registre vide, requête du quota partagé exécutable.
3. CI verte sur `growthos/mvp` et `master` (web) ; `render-checker` et `contract-parity` disponibles pour l'épisode.

## 6. Mise en file et simulation
Le frontend `master` possède déjà le lancement : simulation, confirmation payante, contrôle administrateur et rôle, mise en file conditionnelle et protection contre le double lancement. La planification possède sa propre file et son drapeau. Vérifier les migrations et la configuration en test avant le pilote ; ne pas reconstruire ce parcours.

La fiction `moral_fox_enemy_fr` est préparée pour le pilote. Simulation sans fournisseur (0,30 $ est une hypothèse vocale, à remplacer par le tarif confirmé) :

```bash
python growthos/scripts/story_visual_local_run.py --fixture moral_fox_enemy_fr --voice-rate 0.30 --cap 1
```

Le plafond borne les réservations avant les appels, mais ne garantit pas la facture si le coût réel dépasse une retenue. Un coût inconnu exige une réconciliation humaine. Le rendu local ne valide pas la file, les permissions ni la reprise du worker.

## 7. Déroulé du jour J (après autorisation)
1. Poser la configuration du §4 sur l'environnement de test ; relancer le pré-contrôle : PRÊT.
2. Activer les deux drapeaux sur le test seulement. Créer le projet (simulation → script validé) puis lancer **un** épisode.
3. Surveiller : état du job, dépense cumulée (somme des lignes `story-visual-ledger-*` du content_item), absence de relance en boucle.
4. **Arrêt d'urgence** : retirer `STORY_VISUAL_ENABLED` (refus avant crédit) ; annuler le job et réconcilier les appels déjà engagés.
5. Désactiver les drapeaux. Conserver le MP4, le rapport de coût et le registre ; supprimer le content_item de test si besoin (cascade).

## 8. Autorisations à donner (rien n'est lancé sans elles)
1. Tarif réel de la voix et plafond du pilote (recommandé 1,00 $).
2. Appels payants : OpenAI Images (≈ 8 appels nominaux ; au plus quelques dizaines, bornés par le plafond et par 3 tentatives par scène) et ElevenLabs (8 synthèses nominales) ;
   **aucun** appel au planificateur.
3. Environnement de test, compte administrateur et clés (à poser par vous, jamais dans le dépôt).
4. Activation des drapeaux (par un humain, test uniquement).
5. Choix explicite du parcours de test et validation des garde-fous de mise en file existants.

## 9. Critères d'acceptation du pilote (GO / NO-GO)
| Critère | Seuil |
|---|---|
| Coût réel mesuré | ≤ 0,50 $, aucune ligne `unpriced`, `complete = true` |
| Cohérence du personnage | grille d'identité ≥ 13/16 (protocole du pilote artistique) |
| Lisibilité mobile des sous-titres | sous-titres Faceloop présents et lisibles (contrôle `subtitles.issues` + revue humaine) |
| Synchronisation | dérive audio/vidéo ≤ 0,15 s ; aucun recouvrement de légendes |
| Rendu | `render-checker` sans défaut bloquant ; MP4 1080×1920 H.264/AAC |
| Fiabilité | zéro relance payante en boucle ; total du registre = dépense du rapport |
| Qualité perçue | jugement artistique du propriétaire (humain) |

NO-GO si : un coût inconnu, un dépassement du plafond, une relance qui repaye, un personnage incohérent, un texte illisible, ou un défaut bloquant du rendu.

## 10. Limites connues (assumées)
- Garantie de concurrence du plafond : dépend de la contrainte `unique` de `content_assets` (à confirmer par la requête du §5).
- Quota partagé non strictement atomique (borné par la concurrence du workflow, la réclamation atomique et la réservation de crédit).
- Une retenue « incertaine » (timeout) n'est jamais libérée automatiquement.
- La qualité visuelle et la cohérence du personnage n'ont jamais été mesurées sur un épisode complet : c'est l'objet du pilote.
