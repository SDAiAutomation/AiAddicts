# Story Studio animé — runbook d'exploitation (PR G du plan Gate 4)

Date : 2026-10-24. Statut : **document uniquement. L'animation n'est pas activée, pas déployée, et ne peut pas tourner en production aujourd'hui** (voir §2). Légende : **[VÉRIFIÉ]** lu dans le code ou exécuté ; **[À CONSTRUIRE]** absent ; **[À VÉRIFIER]** supposé.

## 1. Où ça tourne [VÉRIFIÉ, `.github/workflows/growthos-worker.yml`, `engine/repo.py`]
Le « worker » est un job GitHub Actions `ubuntu-latest` (planifié toutes les 10 min, `worker.py --until-idle`, **45 min**, file traitée **en série**, un seul passage à la fois). Il porte les secrets de production (service role Supabase, ElevenLabs, OpenAI…). `repo.reclaim_stale_generating_items` remet en file tout item resté `generating` plus de **15 minutes** sans mise à jour de `updated_at`.

## 2. Pourquoi rien ne peut tourner aujourd'hui (et c'est voulu)
| Prérequis | État |
| --- | --- |
| `STORY_ANIMATION_ENABLED` transmis au job depuis une variable de dépôt | **[À CONSTRUIRE]** : le workflow ne le transmet pas ⇒ le flag est toujours OFF dans le job, même si on crée la variable. Un script animé est refusé avant tout crédit. |
| Godot 4.7.2 + xvfb + Mesa installés dans le job (avec somme SHA-512), seulement quand un contenu animé est en file | **[À CONSTRUIRE]** (modèle : détection `scripts/queue_needs_explainer.py`). Mesuré hors production : 51,5 s de rendu + 19 s d'encodage pour 21,6 s de vidéo sur `ubuntu-latest` (run 40115329358). |
| Pack de personnages sur le runner (`STORY_PACK_DIR`) | **[À CONSTRUIRE]** et **non résolu** : les sprites ne sont pas dans Git. Piste : bucket privé `story-packs`, téléchargement au démarrage du job avec clé de service, vérification SHA-256 du manifeste. |
| `GODOT_BIN`, `STORY_RENDER_LAUNCHER` (`xvfb-run -a -s "-screen 0 1280x2048x24"`), `STORY_RENDER_TIMEOUT_S` | **[À CONSTRUIRE]** dans le workflow. |
| Droits d'usage commercial des images et des voix | **Bloquant avant toute diffusion** (cf. plan §15). |
Même avec le flag activé par erreur, `ports.ready()` refuse tant que Godot ou le pack manquent, **avant** la réservation du crédit [VÉRIFIÉ par test].

### 2 bis. État après R1 (préparé, **inactif**, rien d'appliqué)
- **Workflow dédié** `.github/workflows/story-animation-worker.yml` : déclenchement manuel seulement (ni planification, ni push, ni PR), job ignoré tant que la variable de dépôt `STORY_ANIMATION_ENABLED` n'est pas `'true'`, secrets limités au nécessaire (pas de Pexels, de cron ni d'URL du site), Godot téléchargé avec vérification SHA-512, pack récupéré puis vérifié avant le rendu. Le workflow du worker principal n'est **pas modifié** et ne reçoit toujours pas le flag.
- **`growthos/animation_worker.py`** : ne réclame que les histoires animées (`engine/story_animation/claim.py`, mise à jour conditionnée au statut `queued`), quitte immédiatement si son propre flag est éteint.
- **Packs** : `engine/story_animation/pack_fetch.py` (manifeste SHA-256 exact, taille, liste fermée de fichiers, installation atomique, ancien pack conservé en cas d'échec) ; commandes `pack-manifest` et `fetch-pack` de la CLI ; migration **en attente** `growthos/supabase/pending/story_packs_bucket.sql` (bucket privé `story-packs`, aucune politique : accès service role seulement).
- **Reste à faire avant toute activation** : appliquer la migration sur une branche Supabase isolée ; produire le manifeste du pack validé (`pack-manifest`) et déposer manifeste + 23 PNG dans le bucket avec la clé de service (étape manuelle revue) ; tester le workflow en le déclenchant à la main sur la branche isolée ; relecture juridique.

## 3. Activation (quand tout est prêt) — dans cet ordre, une étape à la fois
1. Branche Supabase isolée (jamais le projet partagé Preview/Production) ; `ADMIN_USER_IDS` renseigné.
2. Ajouter au workflow : détection d'un contenu animé en file, installation de Godot (checksum), téléchargement du pack, variables `STORY_ANIMATION_ENABLED=${{ vars.STORY_ANIMATION_ENABLED || 'false' }}` et ci-dessus. Revue humaine de ce diff (le job porte les secrets de production).
3. Une organisation de test, un auteur administrateur, `STORY_ANIMATION_ENABLED=true`, **une** vidéo ; vérifier §5.
4. Bêta fermée (liste d'administrateurs) ; revue quotidienne des requêtes §5 pendant au moins une semaine.

## 4. Variables du worker pour l'animé
| Variable | Rôle | Défaut |
| --- | --- | --- |
| `STORY_ANIMATION_ENABLED` | active la branche animée (`1/true/yes/on`) | absent = OFF |
| `GODOT_BIN` | chemin de l'exécutable Godot | vide ⇒ refus avant crédit |
| `STORY_PACK_DIR` | dossier du pack (23 PNG validés par nom et taille) | vide ⇒ refus avant crédit |
| `STORY_RENDER_LAUNCHER` | préfixe de lancement (`xvfb-run …`) | vide |
| `STORY_RENDER_TIMEOUT_S` | délai maximal du rendu | 900 |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_USD_PER_1K_CHARS` | voix et estimation de coût (0,18 dans le workflow actuel ; 0,3 par défaut du code) | secret existant |

## 5. Surveillance — requêtes de contrôle [À VÉRIFIER sur une branche Supabase avant usage]
Événements (`product_events`, colonnes `event`, `props`, `created_at` [VÉRIFIÉ dans la migration]) :
```sql
select date_trunc('day', created_at) d, event, count(*)
from product_events
where props->>'renderer' = 'rig_v1' or event = 'generation_failed'
group by 1, 2 order by 1 desc;
```
Échecs récents d'animation (message affiché à l'auteur, limité à 2 000 caractères) :
```sql
select id, updated_at, left(error, 200) from content_items
where status = 'failed' and script->'story'->>'version' = '2' order by updated_at desc limit 20;
```
Crédits : pour chaque contenu animé, **débits − remboursements** doit valoir 0 si l'essai a échoué et au plus le crédit dû si réussi :
```sql
select related_content_item_id, sum(delta) as net, count(*) as lignes
from credits_ledger
where related_content_item_id in (select id from content_items where script->'story'->>'version' = '2')
group by 1 having sum(delta) < -1 order by 2;
```
Éléments bloqués : `status = 'generating'` et `updated_at` plus ancien que 20 minutes (le battement de vie rafraîchit toutes les 60 s, donc un rendu long reste « vivant » [VÉRIFIÉ par test]).

Alertes recommandées (à créer, aujourd'hui inexistantes) : ≥ 2 échecs animés consécutifs ; consommation ElevenLabs mensuelle > 80 % (compte Creator : 121 032 caractères/mois, 30 043 utilisés à l'audit du 2026-10-24) ; durée de job > 30 min ; coût par vidéo estimé > budget.

## 6. Incidents
| Symptôme | Action |
| --- | --- |
| Rendu animé qui échoue en boucle | Mettre `STORY_ANIMATION_ENABLED` à `false` (ou supprimer la variable) : les nouveaux contenus animés sont refusés avant crédit ; les vidéos déjà publiées restent lisibles. Examiner `error` des contenus échoués. |
| Crédit non rendu après un échec | Le remboursement est idempotent : relancer `refund_generation_credit(<id>)` n'inscrit qu'une fois. Vérifier la requête crédits ci-dessus ; en cas d'écart, corriger par une ligne `credits_ledger` explicite, jamais en modifiant le solde à la main. |
| Item resté `generating` | Il est remis en file au bout de 15 min sans battement ; si le worker est mort, la reprise ne débite pas deux fois (réservation idempotente). |
| Quota ElevenLabs épuisé | Les jobs échouent avant le rendu (erreur du fournisseur) et remboursent ; désactiver le flag le temps de recharger. |
| Qualité refusée (`QualityRejected`) | Le crédit est remboursé et l'auteur voit le motif. Un état « à revoir » dédié reste à décider. |
| Fuite suspectée de secret | Le sous-processus Godot reçoit un environnement filtré (variables contenant KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL retirées) ; vérifier les journaux (ni dialogues complets ni URL signées) puis faire tourner les clés concernées. |

## 7. Retour arrière
Flag OFF (§6). Aucune migration SQL n'est livrée par ce chantier : rien à défaire en base. Revenir sur `assembler.py` revient à supprimer 3 lignes et une fonction (`_run_animated`) ; les anciens contenus ne sont pas touchés.

## 8. Limites connues de l'exploitation
- Un seul passage de worker à la fois, file en série : une vidéo animée d'environ 22 s occupe le job 1 à 2 minutes ; une file d'animations peut retarder les vidéos Standard/Quiz (à surveiller, pas de file dédiée).
- Pas d'isolation réseau du sous-processus Godot (documentée dans `rig_v1.py`, à imposer au niveau du runner).
- Aucune alerte automatique n'existe encore ; les requêtes ci-dessus sont manuelles.
