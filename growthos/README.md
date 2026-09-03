# GrowthOS — MVP dogfooding

Cycle minimal : `script.json` → voix off → vidéo texte-carte sous-titrée → package prêt à publier manuellement.

Portée volontaire de ce cycle 1 (semaines 1-2 du plan "Résultats d'abord") :

- Pas de génération vidéo IA payante. Fond uni + sous-titres brûlés : suffisant pour valider la boucle sur un vrai compte, à coût quasi nul.
- Pas de publication automatique (OAuth TikTok/Meta). La demande d'app développeur prendrait des semaines à elle seule. Le script produit une caption prête + une checklist, la publication reste manuelle.
- Un seul provider voix (ElevenLabs), pas de fallback : ce n'est pas un besoin réel à ce stade.

## Installation

```bash
pip install -r requirements.txt
# ffmpeg doit être installé sur la machine (apt install ffmpeg / brew install ffmpeg)
cp .env.example .env   # puis renseigner ELEVENLABS_API_KEY et SUPABASE_SERVICE_ROLE_KEY
bash scripts/install-git-hooks.sh   # garde-fou anti-secret sur `git commit` (voir ci-dessous)
```

Versions des dépendances épinglées (`==`) sur ce qui a été testé — les mettre à jour délibérément.

### Garde-fou anti-secret

`scripts/install-git-hooks.sh` pointe `core.hooksPath` sur `scripts/githooks/`. Le hook `pre-commit` (bash, sans dépendance) bloque tout commit touchant `growthos/` qui contient une clé Supabase `service_role` (JWT `role=service_role`), une `SUPABASE_SERVICE_ROLE_KEY` / `ELEVENLABS_API_KEY` renseignée, ou un fichier `.env`. Faux positif confirmé : `git commit --no-verify`. Désactiver : `git config --unset core.hooksPath`.

## Lancer une génération

```bash
python main.py content/scripts/exemple-01.json
python main.py content/scripts/exemple-01.json --voice 21m00Tcm4TlvDq8ikWAM
```

### Choix de la voix

Résolue à la génération, premier élément renseigné l'emporte :

1. l'option `--voice <id>` (pratique pour tester deux voix sur le même script)
2. le champ `voice_id` du script (optionnel)
3. `config/voices.json`, indexé par la `niche` du script — c'est le « choix selon le topic »
4. la clé `default` de `config/voices.json`

Pas de sélecteur interactif : le pipeline reste scriptable/batchable. Renseigne au moins la clé `default` (ou une entrée par niche) dans `config/voices.json` avec un ID copié depuis ElevenLabs → My Voices. La ligne `content_items` enregistre la voix réellement utilisée.

Produit, dans `output/<compte>-<titre>/` :

1. `audio/` — un mp3 par bloc + `full.wav` (voix off complète, assemblée sans blancs entre blocs)
2. `captions.srt` — sous-titres synchronisés sur la durée réelle de chaque bloc
3. `final/*.mp4` — vidéo finale (fond uni + sous-titres brûlés)
4. `publish/caption.txt` — caption + hashtags prêts à copier-coller
5. `publish/checklist.md` — checklist avant publication manuelle (avec la commande `log_metrics.py` pré-remplie)

Relancer sur le même script est peu coûteux : les blocs audio et la vidéo finale déjà
présents dans `output/<slug>/` sont réutilisés. Supprime ce dossier pour forcer une
reconstruction propre (par ex. après avoir modifié le texte du script).

Et dans Supabase : l'organisation et le compte sont créés s'ils n'existent pas encore, puis une ligne `content_items` (statut `video`, script complet en JSON, chemin de la vidéo). L'id du content_item s'affiche en fin de run, à réutiliser pour `log_metrics.py`.

## Écrire une nouvelle histoire

Un script est un fichier JSON dans `content/scripts/` avec `title`, `niche`, `account`, `hashtags`, et une liste `blocks` (`role`: `hook` / `point` / `cta`, `text`: le texte narré). Optionnels : `platform` (défaut `tiktok`), `organization` (défaut `GrowthOS Dogfooding`), `aspect_ratio` (`9:16` / `1:1` / `16:9`, défaut `9:16`), `voice_id` (sinon résolu via `--voice` ou `config/voices.json`, cf. plus haut). Voir `exemple-01.json`.

## Suivi hebdomadaire

Après chaque publication réelle, logger les métriques dans Supabase plutôt que dans un fichier :

```bash
python log_metrics.py <content_item_id> --mark-published \
  --views 1200 --watch-time-pct 45.5 --likes 30 --comments 5 --shares 2 \
  --followers-delta 8 --leads 3
```

`--mark-published` (seulement au premier log après la publication réelle) passe le `content_item` en statut `published`. Chaque appel ajoute une ligne dans `content_performance`, liée au `content_item`. Pas de dashboard à ce stade, c'est la V0 volontairement plate. Le Dashboard produit (§4.1 du design system) viendra une fois la boucle validée.

## Base de données (Supabase)

Projet Supabase dédié, séparé de tout autre projet : **growthos**, ref `lclesqfokgetznhepgmj`, région `eu-west-1`, plan gratuit.

Schéma complet posé d'avance (comptes, rôles, tokens OAuth, stratégie vivante, pipeline de contenu, crédits, audit), pas seulement scripts + métriques :

| Table | Rôle |
|---|---|
| `organizations` | tenant (workspace agence ou solopreneur), plan, solde de crédits |
| `profiles` / `organization_members` | utilisateurs + rôle (`owner` / `strategist` / `editor` / `client_viewer`) |
| `accounts` | comptes faceless (plateforme, niche, statut) |
| `account_oauth_tokens` | tokens OAuth **chiffrés côté application** avant insertion (jamais en clair) |
| `strategies` | stratégie vivante par compte (objectifs, audience, ton, score de maturité) |
| `content_items` / `content_performance` | pipeline idée → script → vidéo → publié, et mesures par vidéo |
| `insights` / `recommendations` | mémoire de compte (hooks/formats gagnants) et recommandations hebdo avec score de confiance |
| `credits_ledger` | grand livre des crédits consommés |
| `audit.events` | journal d'audit **append-only** (triggers qui bloquent tout UPDATE/DELETE, même en SQL direct) |

Isolation multi-tenant : RLS activé sur toutes les tables, chaque politique passe par `organization_members` (fonctions `internal.current_user_org_ids()` / `internal.has_org_role()`, dans un schéma non exposé par l'API pour ne pas devenir un endpoint RPC public). Advisor sécurité Supabase : 0 alerte.

Le pipeline écrit via `service_role` (contourne RLS) et ne crée jamais de `profiles` / `organization_members`. Le jour où une vraie auth arrive, un utilisateur connecté ne verrait rien tant qu'il n'est pas rattaché. Une fois inscrit dans Supabase Auth, le relier aux organisations existantes :

```bash
python scripts/backfill_membership.py --list                 # état actuel
python scripts/backfill_membership.py --email moi@x.com --dry-run
python scripts/backfill_membership.py --email moi@x.com       # crée profiles + organization_members (owner) pour les orgs orphelines
```

`content_items` / `content_performance` n'ont pas de colonne `organization_id` : leur RLS résout l'org via `account_id → accounts.organization_id`.

Migrations SQL versionnées dans `supabase/migrations/` (déjà appliquées sur le projet hébergé). Pour rejouer sur un autre projet :

```bash
supabase link --project-ref lclesqfokgetznhepgmj
supabase db push
```

Deux clés dans `.env` :
- `SUPABASE_ANON_KEY` — publique par design (protégée par RLS), déjà dans `.env.example`.
- `SUPABASE_SERVICE_ROLE_KEY` — secrète, **contourne RLS**, à récupérer sur le dashboard Supabase (Project Settings → API) et à garder strictement côté backend (écriture `audit.events`, ajustement de crédits, jobs).

`config.py` et `engine/db.py` posent la connexion (`get_client()` en anon/RLS, `get_service_client()` en service_role). Le pipeline (`main.py` → `engine/assembler.py`) et `log_metrics.py` écrivent tous les deux via `get_service_client()` : ce sont des scripts lancés directement par le propriétaire du compte, il n'y a pas de session Supabase Auth à scoper en anon/RLS ici. `get_client()` est prêt pour le jour où une vraie interface (avec login) arrive.

## Tests

```bash
python -m unittest discover -s tests
```

Aucun appel réseau ni ffmpeg dans les tests (logique pure : validation de script, timestamps SRT, config Supabase). `engine/repo.py` (accès DB) n'est pas testé unitairement pour la même raison que `tts.py`/`video.py` : il ne fait rien d'autre que des appels réseau.

## Prochaines étapes

Voir le plan sur 6-8 semaines : Quality Gate simple + analytics de base (semaines 3-4), corrections de friction + début de mémoire de compte (semaines 5-6), stabilisation pour la mise en public des résultats (semaines 7-8).
