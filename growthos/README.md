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

Et dans Supabase : l'organisation et le compte sont créés s'ils n'existent pas encore, puis une ligne `content_items` (statut `video`, script complet en JSON). La vidéo finale est aussi uploadée vers le bucket Storage public `content-videos` (`engine/storage.py`) — `video_url` devient cette URL publique plutôt qu'un chemin local (si l'upload échoue, on retombe silencieusement sur le chemin local, le run n'échoue pas pour autant). L'id du content_item s'affiche en fin de run, à réutiliser pour `log_metrics.py`.

## Écrire une nouvelle histoire

Un script est un fichier JSON dans `content/scripts/` avec `title`, `niche`, `account`, `hashtags`, et une liste `blocks` (`role`: `hook` / `point` / `cta`, `text`: le texte narré). Optionnels : `platform` (défaut `tiktok`), `organization` (défaut `GrowthOS Dogfooding`), `aspect_ratio` (`9:16` / `1:1` / `16:9`, défaut `9:16`), `language` (`fr` / `en` / `es` / `de` / `it` / `pt`, défaut `fr` — informatif, la voix ElevenLabs `eleven_multilingual_v2` détecte la langue depuis le texte, pas de `language_code` à passer), `voice_id` (sinon résolu via `--voice` ou `config/voices.json`, cf. plus haut). Voir `exemple-01.json`.

`content_goal` choisit le critère de durée : `reach` (défaut, vidéo resserrée
pour la portée) ou `monetization` (au moins 60 secondes pour l'éligibilité
TikTok). Le rendu découpe automatiquement les blocs narratifs en plans de
3 secondes maximum pour maintenir le rythme visuel.

Le cache est versionné par une empreinte du script, de la voix, des réglages
et du code de génération. Modifier l'un de ces éléments crée un nouveau
dossier `output/<slug>-<empreinte>/` et empêche la réutilisation d'une ancienne
vidéo portant le même titre.

### Visuels de bloc

`engine/visuals.py` produit un visuel par bloc, derrière les sous-titres :

- **`visual_style` = `stock_footage`** → un **clip vidéo Pexels** par bloc (gratuit, `PEXELS_API_KEY`), photo Pexels en repli. Pour les sujets concrets (sport, cuisine, voyage, actu). `engine/video.py` recadre le clip plein cadre 9:16, le boucle/coupe à la durée du bloc, sans Ken Burns.
- **sinon** (`OPENAI_API_KEY`) → une **image IA** par bloc (`VISUALS_BLOCKS_PER_IMAGE`, défaut 1 ; mettre `3` pour regrouper et diviser le coût), Pexels photo en repli. Ken Burns (zoom lent) sur l'image.
- **aucune clé** → fond couleur unie.

### Pipeline d'images de scène

`engine/visuals.fetch_block_images` orchestre, pour chaque scène (groupe de blocs) :

```
image_style_bible      -> identité visuelle du script (1x, réutilisée sur toutes les scènes)
image_character_bible  -> fiche personnage conditionnelle (1x, réutilisée sur toutes les scènes)
image_prompt_builder   -> assemble le prompt final d'UNE scène
image_model_router     -> modèle/qualité selon l'usage (preview/final/edit)
openai_images          -> appel API OpenAI (retry/backoff, generate/edit)
image_quality_control  -> QC vision OPT-IN (IMAGE_QC_ENABLED) + boucle edit ciblé/régénération
```

**Cohérence des personnages** : chaque appel image IA est une génération texte indépendante — sans description physique réinjectée, un prénom qui sonne humain (« Léo ») fait dériver un ourson vers un petit garçon d'un bloc à l'autre. Deux champs de script optionnels corrigent ça, concaténés en tête de **chaque** prompt de scène :

- **`characters`** : liste de `{ "name", "description", "negative"? }`. `description` est l'apparence **fixe** (espèce, couleur, taille, vêtements, traits, style de dessin) ; `negative` la contrainte à ne jamais enfreindre.
- **`visual_style_prompt`** (Faceloop) ou **`visual_style`** (CLI) : la consigne de style graphique, identique sur toutes les scènes. Faceloop écrit la phrase complète du pack choisi dans `visual_style_prompt` (catalogue `growthos-web/.../content/visual-styles.ts` : `storybook`, `pixar_3d`, `anime`, `comic_book`, `gta_loading`, `cinematic_real`, `stock_footage`, `flat_color`). En CLI, `visual_style` accepte soit un de ces ids (traduit par `image_style_bible._VISUAL_STYLE_PROMPTS`), soit une phrase libre. `visual_style_prompt` l'emporte s'il est présent. La Style Bible ajoute en plus une avoid-list (logo/filigrane/anatomie distordue/etc.) et des règles de composition portrait, appliquées à tous les styles.

**Testé et écarté** : dériver le visuel d'une scène de celui de la scène précédente via `/v1/images/edits` (ancrage) garde le personnage mais fige la pose et le cadrage d'une scène à l'autre — chaque scène est donc générée indépendamment, texte seul, en parallèle. `/v1/images/edits` reste utilisé, mais uniquement pour la correction **ciblée** d'une image déjà générée (`openai_images.edit_image`, "corrige la main, garde tout le reste").

**Modèle/qualité** (`engine/image_model_router.py`) : `OPENAI_IMAGE_MODEL` (défaut `gpt-image-1-mini`) / `OPENAI_IMAGE_QUALITY` (`low`/`medium`/`high`, défaut `medium` ≈ 0,03 $/image ; `high` ≈ 0,06 $) restent les réglages de repli du mode **"final"** (seul utilisé aujourd'hui par le pipeline). `IMAGE_MODEL_PREMIUM`/`IMAGE_FINAL_QUALITY`, `IMAGE_MODEL_FAST`/`IMAGE_PREVIEW_QUALITY` (mode "preview", pas encore branché par défaut) et `IMAGE_MODEL_EDIT`/`IMAGE_EDIT_QUALITY` (mode "edit") permettent de différencier — voir `.env.example`. `input_fidelity=high` n'est activé que sur `gpt-image-1` (pas sur `-mini`).

**Contrôle qualité vision** (`engine/image_quality_control.py`, `IMAGE_QC_ENABLED=false` par défaut — capacité opt-in, coût/latence supplémentaires) : score 0-100 par image (adhérence au prompt, cohérence personnage, anatomie, composition...), décision `APPROVE`/`EDIT`/`REGENERATE` selon `IMAGE_QC_THRESHOLD_APPROVE`/`IMAGE_QC_THRESHOLD_EDIT`. Boucle plafonnée à `MAX_IMAGE_ATTEMPTS` (défaut 3) ; au-delà, l'image est gardée avec un flag `manualReview` (fait basculer le content_item en `quality_check`, jamais d'échec silencieux). Nécessite `IMAGE_QC_MODEL` (pas de défaut codé en dur — vérifier le modèle vision disponible sur le compte OpenAI utilisé avant d'activer). Rapport agrégé (coût estimé, versions, détail par scène) écrit dans `content_items.image_generation_report`.

Voir `exemple-02-histoire.json`.

### Format quiz vidéo

Le parcours produit peut proposer cinq recettes stables : `quick`,
`true_false`, `riddle`, `logo` et `impossible`. Une recette fournit le type, la
difficulté et le compte à rebours par défaut ; chaque question peut encore
surcharger sa durée. Les types visuels `logo` et `image` exigent un champ
`visual`. Le rendu affiche aussi la progression (`QUESTION 2/5`).

Un script peut utiliser `"content_format": "quiz"` avec un objet `quiz` à la
place des `blocks`. Le moteur compile automatiquement chaque question en deux
scènes : question avec choix et compte à rebours, puis révélation avec une
courte explication. Le rendu reste un MP4 destiné à TikTok, Reels ou Shorts ;
les réponses ne sont pas cliquables.

```json
{
  "title": "Quiz express sur l'espace",
  "niche": "culture-generale",
  "account": "test-account-01",
  "content_format": "quiz",
  "quiz": {
    "topic": "l'espace",
    "questions": [{
      "question": "Quelle planète est la plus proche du Soleil ?",
      "choices": ["Vénus", "Mercure", "Mars"],
      "correct_choice": 1,
      "explanation": "Mercure est la première planète du système solaire.",
      "countdown_seconds": 3
    }]
  }
}
```

Contraintes MVP : 1 à 5 questions, 2 à 4 choix distincts, index de réponse
correcte en base zéro, compte à rebours de 1 à 10 secondes. Voir
`content/scripts/exemple-quiz.json` pour un exemple complet.

### Style des sous-titres

`caption_style` (optionnel, défaut `bold_stroke`) choisit le rendu des sous-titres brûlés — porté par un fichier `.ass` généré par `engine/captions.write_ass` (libass). Valeurs : `bold_stroke` (blanc gras contour épais), `sleek` (fin, discret), `boxed` (bandeau noir), `neon` (halo bleu), `word_pop` (le mot prononcé passe en jaune et grossit — utilise le timing mot-à-mot). `engine/video.py` détecte le `.ass` et laisse libass appliquer le style embarqué ; sans `.ass`, repli sur l'ancien style unique via `force_style`.

Un cue trop large (mot très long, ou 3 mots longs) passe sur 2 lignes centrées (`WrapStyle: 0`) et voit sa police réduite au-delà de ~22 caractères — pas de texte rogné aux bords du cadre.

### Contrôle qualité automatique

À la fin de la génération, `engine/quality.score_generation` note la vidéo sur 100 à partir de signaux objectifs : voix off ≥ 60s, toutes les scènes ont un visuel, densité de sous-titres plausible, fichier final non vide. Score ≥ 70 → statut `video` (publication en un clic). Score < 70 → statut `quality_check` + `content_items.quality_flags` (liste des motifs), affichés sur `/content/[id]` côté growthos-web : l'opérateur regarde, puis publie quand même ou régénère.

## Worker (file de génération depuis le front)

`growthos-web` (repo séparé, Next.js) ne peut pas lancer ElevenLabs/ffmpeg
depuis Vercel : quand on clique « Générer la vidéo » sur un script, le front
se contente de passer le `content_item` en `status='queued'` (le script JSON
est déjà dedans, construit au même schéma que `content/scripts/*.json`).
`worker.py`, lancé à côté (poste de travail ou petit serveur avec ffmpeg),
poll cette file, réclame un job (`status='generating'`), génère, puis remet
`status='video'` ou `status='failed'` + `error`.

```bash
python worker.py                # boucle, poll toutes les 10s
python worker.py --interval 5   # poll plus serré
python worker.py --once         # traite au plus un job puis s'arrête (cron externe)
```

Réutilise le même moteur que `main.py` (`engine/assembler.run_for_content_item`) :
mêmes réutilisations de fichiers déjà générés, même résolution de voix. Différence
avec le CLI : le compte existe déjà (créé via le front), pas de `get_or_create`
organisation/compte, juste une mise à jour de la ligne `content_items` existante.

Avant tout appel payant, le worker réserve atomiquement un crédit via Postgres.
La réservation est idempotente lors d'une reprise après crash et remboursée si la
génération échoue ; deux workers concurrents ne peuvent donc pas consommer le
dernier crédit de la même organisation en parallèle.

## Suivi hebdomadaire

Après chaque publication réelle, logger les métriques dans Supabase plutôt que dans un fichier :

```bash
python log_metrics.py <content_item_id> --mark-published \
  --views 1200 --watch-time-pct 45.5 --likes 30 --comments 5 --shares 2 \
  --followers-delta 8 --leads 3
```

`--mark-published` (seulement au premier log après la publication réelle) passe le `content_item` en statut `published`. Chaque appel ajoute une ligne dans `content_performance`, liée au `content_item`. Pas de dashboard à ce stade, c'est la V0 volontairement plate. Le Dashboard produit (§4.1 du design system) viendra une fois la boucle validée.

Après chaque snapshot, `engine/learning.py` reconstruit la mémoire du compte à
partir de la mesure la plus récente de chaque vidéo. Il calcule un score
pondérant rétention, engagement, partages, abonnés et leads, puis agrège les
mécaniques de hook, sujets et formats dans `insights`. La recommandation
`pending` du compte est mise à jour dans `recommendations` avec un niveau de
confiance lié au nombre de vidéos observées. Les performances brutes restent la
source de vérité si cette actualisation dérivée échoue.

## Base de données (Supabase)

Projet Supabase dédié, séparé de tout autre projet : **growthos**, ref `lclesqfokgetznhepgmj`, région `eu-west-1`, plan gratuit.

Storage : bucket public `content-videos` (une vidéo = `<content_item_id>.mp4`, upsert à la régénération). Public en lecture (URL directe, pas de signature), écriture réservée à `service_role` — RLS par défaut = deny, aucune policy `storage.objects` à écrire puisque seul le worker (service_role) y touche.

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

Aucun appel réseau ni ffmpeg dans les tests (logique pure : validation de script, timestamps SRT, config Supabase, Style/Character Bible, prompt builder, routage modèle, parsing/scoring du contrôle qualité image). `engine/repo.py` (accès DB) n'est pas testé unitairement pour la même raison que `tts.py`/`video.py`/`openai_images.py` : il ne fait rien d'autre que des appels réseau.

## Prochaines étapes

Voir le plan sur 6-8 semaines : Quality Gate simple + analytics de base (semaines 3-4), corrections de friction + début de mémoire de compte (semaines 5-6), stabilisation pour la mise en public des résultats (semaines 7-8).
