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
```

## Lancer une génération

```bash
python main.py content/scripts/exemple-01.json
```

Produit, dans `output/<compte>-<titre>/` :

1. `audio/` — un mp3 par bloc + la voix off complète assemblée
2. `captions.srt` — sous-titres synchronisés sur la durée réelle de chaque bloc
3. `final/*.mp4` — vidéo finale (fond uni + sous-titres brûlés)
4. `publish/caption.txt` — caption + hashtags prêts à copier-coller
5. `publish/checklist.md` — checklist avant publication manuelle

## Écrire une nouvelle histoire

Un script est un fichier JSON dans `content/scripts/` avec `title`, `niche`, `account`, `voice_id`, `hashtags`, et une liste `blocks` (`role`: `hook` / `point` / `cta`, `text`: le texte narré). Voir `exemple-01.json`.

## Suivi hebdomadaire

Après chaque publication réelle, ajouter une ligne dans `metrics/suivi-hebdo.csv` (6 métriques du plan "Résultats d'abord" : publications/semaine, vues moyennes, watch time, abonnés nets, engagement, leads). Pas de dashboard à ce stade, c'est la V0 volontairement plate. Le Dashboard produit viendra une fois la boucle validée.

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

Migrations SQL versionnées dans `supabase/migrations/` (déjà appliquées sur le projet hébergé). Pour rejouer sur un autre projet :

```bash
supabase link --project-ref lclesqfokgetznhepgmj
supabase db push
```

Deux clés dans `.env` :
- `SUPABASE_ANON_KEY` — publique par design (protégée par RLS), déjà dans `.env.example`.
- `SUPABASE_SERVICE_ROLE_KEY` — secrète, **contourne RLS**, à récupérer sur le dashboard Supabase (Project Settings → API) et à garder strictement côté backend (écriture `audit.events`, ajustement de crédits, jobs).

Rien dans le code Python n'utilise encore la base (le pipeline actuel reste sur `content/scripts/*.json` + `metrics/suivi-hebdo.csv`). `config.py` et `engine/db.py` posent la connexion (`get_client()` en anon/RLS, `get_service_client()` en service_role) pour le prochain cycle : brancher `content_items`/`content_performance` à la place des fichiers plats.

## Tests

```bash
python -m unittest discover -s tests
```

Aucun appel réseau ni ffmpeg dans les tests (logique pure : validation de script, timestamps SRT, CSV de métriques).

## Prochaines étapes

Voir le plan sur 6-8 semaines : Quality Gate simple + analytics de base (semaines 3-4), corrections de friction + début de mémoire de compte (semaines 5-6), stabilisation pour la mise en public des résultats (semaines 7-8).
