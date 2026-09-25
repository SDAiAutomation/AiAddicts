# AutoEdit — contrat frontend/backend v0

Ce document définit le contrat partagé entre le frontend `growthos-web` et le backend GrowthOS. Deux profils sont disponibles : `sports` pour les temps forts sans sous-titres et `general` pour les vlogs, interviews et podcasts avec transcription de la parole.

## Création d'un job

Le frontend collecte une vidéo et une configuration. L'upload peut être direct vers le backend ou vers un stockage temporaire, selon l'implémentation choisie par Claude Code.

```ts
type AutoEditCreateInput = {
  file: File
  profile: "sports" | "general"
  focus: "best" | "player" | "goals"
  playerNumber?: string
  style: "hype" | "cinematic" | "clean" | "emotional"
  durationSeconds: 15 | 30 | 60
}
```

Le backend répond rapidement avec un identifiant de job. Il ne doit pas maintenir la requête HTTP ouverte pendant l'analyse vidéo.

Le profil `sports` n'ajoute jamais de sous-titres et conserve le son original ; si la source est sans piste audio ou quasi muette, Eleven Music peut produire une piste instrumentale adaptée au style. Le profil `general` transcrit uniquement le montage sélectionné avec ElevenLabs Scribe et réutilise le rendu de sous-titres mot par mot de Generate. Une panne de musique ou de transcription ne bloque pas le rendu : elle ajoute un signal de revue manuelle.

```ts
type AutoEditCreateResponse = {
  jobId: string
  status: "queued"
}
```

## États du job

```ts
type AutoEditStatus =
  | "queued"
  | "uploading"
  | "analyzing"
  | "planning"
  | "rendering"
  | "review"
  | "completed"
  | "failed"
```

Le statut doit être lisible sans connaître les détails internes du worker. Une réponse de polling ou un événement temps réel suit cette forme :

```ts
type AutoEditJob = {
  jobId: string
  status: AutoEditStatus
  progress: number | null // 0..100, null si inconnu
  stageLabel: string | null
  input: {
    filename: string
    durationSeconds: number | null
  }
  configuration: {
    profile: "sports" | "general"
    focus: "best" | "player" | "goals"
    playerNumber: string | null
    style: "hype" | "cinematic" | "clean" | "emotional"
    durationSeconds: 15 | 30 | 60
  }
  error: { code: string; message: string; retryable: boolean } | null
  createdAt: string
  updatedAt: string
}
```

Le frontend affiche `stageLabel` comme texte utilisateur et utilise `progress` uniquement quand il est fourni. Il ne déduit jamais un pourcentage à partir d'un statut.

## Analyse et événements détectés

Les événements sont persistés afin que plusieurs montages puissent réutiliser une seule analyse.

```ts
type AutoEditEvent = {
  id: string
  type: "goal" | "shot" | "pass" | "dribble" | "defense" | "celebration" | "highlight" | "audio_peak" | "scene_change"
  startSeconds: number
  endSeconds: number
  score: number | null // score interne 0..100, pas une prédiction de vues
  confidence: number | null // 0..1
  subject: string | null
  notes: string | null
}
```

## Edit Decision List

Le modèle propose un EDL ; le moteur déterministe l'exécute.

```ts
type AutoEditDecision = {
  source: string
  startSeconds: number
  endSeconds: number
  speed: number
  eventId: string | null
  cropTarget: string | null
  effect: "slow_motion" | "none" | null
  caption: string | null
}

type AutoEditPlan = {
  version: string
  durationSeconds: number
  style: "hype" | "cinematic" | "clean" | "emotional"
  decisions: AutoEditDecision[]
}
```

L'EDL doit être validé avant rendu : timecodes dans les limites de la source, durée positive, vitesse positive, nombre de clips borné et sources autorisées. Une erreur de validation passe le job en `failed` avec `retryable` explicite.

## Résultat

```ts
type AutoEditResult = {
  jobId: string
  status: "completed" | "review"
  videoUrl: string | null
  posterUrl: string | null
  expiresAt: string | null
  purged: boolean
  plan: AutoEditPlan
  eventsUsed: string[]
  quality: {
    score: number | null
    flags: string[]
    manualReview: boolean
  }
  usage: {
    analysisCost: number | null
    renderCost: number | null
    currency: string
  }
}
```

`videoUrl` et `posterUrl` peuvent rester `null` pendant `review`.

**Confidentialité et rétention.** Le montage est rendu dans le bucket privé `autoedit-results` (`<organization_id>/<job_id>/result.mp4` et `poster.jpg`), jamais dans le bucket public des vidéos générées. `videoUrl` et `posterUrl` sont des URL **signées temporaires** (2 h) fabriquées par `GET /api/autoedit/jobs/:jobId` à chaque appel, après lecture du job sous RLS : le frontend ne doit ni les stocker, ni les partager, mais relire le job pour en obtenir de nouvelles. `expiresAt` est la date à laquelle la source et le montage seront supprimés (`AUTOEDIT_RETENTION_DAYS`, 7 jours par défaut, posée à la fin du job, en revue comme en échec) ; `purge_autoedit.py` les supprime chaque jour. Après suppression, `purged` vaut `true`, les URL restent `null` et le job reste visible comme historique : le frontend doit l'indiquer au lieu d'un lecteur vide. Le frontend doit proposer une revue lorsque `manualReview` vaut `true` ou lorsque `quality.flags` n'est pas vide.

## Règles de frontière

- Le frontend ne calcule pas les highlights, la qualité, les coûts ou les timecodes.
- Le backend ne dépend pas des libellés visuels français/anglais ; il reçoit des identifiants stables.
- Les erreurs sont structurées et localisables côté frontend via `code`.
- Les scores internes ne sont jamais présentés comme une garantie de vues, de viralité ou de monétisation.
- Les fichiers doivent être apportés par l'utilisateur ou couverts par des droits suffisants ; le backend peut refuser un média non conforme à ses règles de licence.
- Les extensions futures ajoutent un `profile` et des types d'événements sans modifier le cycle de job.

## Implémentation backend — squelette (2026-09-23)

Décision produit : infrastructure d'abord, expérimental, sans analyse vidéo payante. **Pas de serveur HTTP Python** : l'app web crée le job, le worker traite la file.

**Jalon livré** : `upload reprenable → autoedit_jobs → claim worker → analyse locale → événements → EDL → rendu FFmpeg → revue`.

- Migration `20260923130000_autoedit_jobs.sql` (NON appliquée en remote tant que non validée) : table `autoedit_jobs`, bucket privé `autoedit-sources`, RPC `reserve_autoedit_credit` / `refund_autoedit_credit`.
- Le frontend (client Supabase de l'utilisateur) : 1) `INSERT` dans `autoedit_jobs` avec seulement `organization_id, input_filename, input_duration_seconds?, profile, focus, player_number?, style, duration_seconds` (statut `uploading` par défaut, `jobId` = `id` retourné) ; 2) upload du fichier vers `autoedit-sources` au chemin exact `<organization_id>/<jobId>/source` ; 3) `UPDATE status = 'queued'` — seule écriture permise (droits au niveau des colonnes + RLS). Un envoi jamais confirmé passe en `failed` (`upload_incomplete`) après 2 h.
- Lecture : `SELECT` sur `autoedit_jobs` (RLS par organisation) pour le polling. Correspondance ligne → contrat : `engine/autoedit.py` `to_job_view` / `to_result_view` (`stage_label` → `stageLabel`, `input_filename` → `input.filename`, `error` = `{code, message, retryable}`, `events`, `plan`, `quality`, `usage`, `video_url`, `poster_url`).
- Statuts posés par le worker réel : `queued → analyzing → planning → rendering → review`. L'analyseur `signals` mesure les ruptures visuelles et les pics audio relatifs avec FFmpeg, fusionne les signaux qui couvrent le même passage, exécute l'EDL et produit une vidéo verticale. La revue reste obligatoire car cette version ne reconnaît pas encore sémantiquement les buts ni les joueurs. L'analyseur `simulated` reste disponible pour les smoke tests et ne produit aucune vidéo.
- Codes d'erreur : `source_missing`, `insufficient_credits`, `plan_invalid`, `upload_incomplete`, `worker_lost`, `internal_error`.
- Crédits : quota commun avec Generate, consommation propre (`related_autoedit_job_id`, raisons `autoedit_*`), coût dans `usage` séparé de `generation_cost_report`. Analyse simulée = 0 crédit ; tarif d'une analyse réelle non mesuré (`AUTOEDIT_CREDIT_COST`, défaut provisoire 1).
- Activation : `AUTOEDIT_ENABLED=true` et `AUTOEDIT_ANALYZER=signals` côté worker (désactivé par défaut) ; le frontend garde la fonctionnalité derrière un état expérimental.
- Événements persistés sur la ligne du job (`events`) pour l'instant ; une table dédiée sera nécessaire quand plusieurs montages devront réutiliser une analyse.
- `AutoEditPlan.version` = `autoedit-plan-v1`. Limite de taille de la source : 500 Mo côté bucket, plafonnée par la limite globale du projet Supabase.
