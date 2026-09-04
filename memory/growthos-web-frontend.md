---
name: growthos-web-frontend
description: GrowthOS frontend — separate repo growthos-web, Next.js + Supabase, started 2026-09-03
metadata:
  type: project
---

Décidé le 2026-09-03 (réponses AskUserQuestion de l'utilisateur) : **app complète**, **Next.js + Supabase**, **repo dédié séparé**, **auth Supabase activée maintenant**.

Emplacement disque : `C:\Users\user2\Desktop\GrowthOS\growthos-web` (frère de `AiAddicts/`, PAS dans le monorepo). Repo GitHub **`SDAiAutomation/growthos-web`** privé, branche `master`. `gh` CLI authentifié (`SDAiAutomation`, keyring). Commits/push : identité passée en `-c user.name/user.email` (pas de `~/.gitconfig` global) ; `git push` depuis le tool marche (creds GCM en cache). `dangerouslyDisableSandbox` pas nécessaire.

Stack : Next.js 16 (App Router, Turbopack), React 19, TS, Tailwind v4, `@supabase/ssr`, `lucide-react`, `cmdk`. Convention Next 16 : `src/proxy.ts` (pas `middleware.ts`) pour la garde de routes.

**Design system** : `docs/design-system.md` (fourni par l'utilisateur 2026-09-03, style Linear/Stripe, anti-AI-slop). Points durs : **light par défaut** (`#F8FAFC`/`#FFFFFF`/`#E2E8F0`/`#0F172A`/`#64748B`), **accent unique `#2563EB`**, dark en opt-in `[data-theme="dark"]` seulement (pas de suivi OS), radius 6/8/12, Lucide (jamais d'emoji), command palette ⌘K obligatoire, tous les états (loading/empty/error/success) sur chaque surface. La 1re version de la Phase 0 était en dark+cyan → refaite (commit `fec9a21`). Tokens dans `src/app/globals.css`, primitives dans `src/components/ui/`, shell dans `src/components/app-shell/`. Voir [[blotato-product-reference]] pour le périmètre produit (style = anti-modèle).

**Architecture génération** : le pipeline Python (ffmpeg/ElevenLabs) ne tourne pas sur Vercel → file de jobs via la DB. Le front insère `content_items` en `status='queued'`, un `worker.py` (à écrire, dans `AiAddicts/growthos/`) poll et lance `assembler.run()` en service_role, le front suit le statut via Realtime. Nécessite 1 migration : ajouter `queued`/`generating` au check `content_items.status` + colonnes `error`, `requested_by`.

### État au soir du 2026-09-03 (HEAD `growthos-web` = `345147f`)

**Phase 0 — FAIT ET VÉRIFIÉ end-to-end** (landing → signup → provisioning auto → login → shell → données RLS scopées). Livré :
- `/` landing publique (hero + aperçu produit CSS + « comment ça marche » en flux numéroté + features + CTA). `/` ajouté à `PUBLIC_PATHS` du proxy.
- `/login` + `/signup` : email+mdp (server actions), **bouton « Continuer avec Google » placé SOUS le formulaire** (préférence utilisateur), séparateur « ou ».
- Inscription self-serve : trigger Postgres `handle_new_user` (migration `AiAddicts/growthos/supabase/migrations/20260903120000`, **déjà appliquée** sur le projet hébergé) → crée `profiles` + orga perso + `organization_members` owner. Vérifié : signup de `sdaiautomation+dogfood1@gmail.com` a bien créé les 3 lignes. `backfill_membership.py` n'est plus nécessaire pour les nouveaux.
- **« Confirm email » est ON** dans Supabase → écran « vérifie ta boîte mail » après signup. L'utilisateur pourrait le passer OFF pour le dogfooding.
- App shell : sidebar 224px repliable + topbar (recherche ⌘K + menu compte) + command palette cmdk. Pages Dashboard (KPI + actions prioritaires + activité récente), Comptes, Contenus (listes RLS), Analytics/Réglages (placeholder).

**Google OAuth — code fait, BLOQUÉ sur config Google Cloud.** `signInWithGoogle` + `/auth/callback` (exchangeCodeForSession) OK. Le test a atteint Google puis **`Erreur 400 redirect_uri_mismatch`** : l'URI `https://lclesqfokgetznhepgmj.supabase.co/auth/v1/callback` n'est pas dans « Authorized redirect URIs » du client OAuth Google (`1016891095673-8c5gs34467l8o3403bl829h617pf06vr`). Client Secret est bien dans Supabase (provider Google activé). **À reprendre demain** : user ajoute l'URI dans Google Cloud → relancer le test navigateur.

Users Supabase : `sdaiautomation@gmail.com` (owner « GrowthOS Dogfooding », uid `8b5223cb-…`, créé à la main + backfill) et `sdaiautomation+dogfood1@gmail.com` (« Test Dogfood — workspace », créé via /signup, non confirmé). Note : l'utilisateur a été **déconnecté** pendant le test OAuth — il devra se reconnecter.

**Polish** : `.gitattributes` fait (`f32b043`). Toggle sidebar + alignement contenu : **fait** (`8e3f8b4`) — bouton replier/déplier remonté dans l'en-tête de la sidebar (n'est plus chevauché par le badge dev Next.js), contenu app `max-w-5xl` sans `mx-auto` (aligné à gauche au lieu de centré).

**Landing page** : resserrée le 2026-09-04 (`3ba5b32`) — l'utilisateur trouvait qu'il y avait trop de boutons signup/login (6 pour un visiteur : header ×2, hero ×2, CTA milieu, footer ×2). Header = « Se connecter » en lien texte discret seulement ; hero = un seul CTA « Créer un compte » ; CTA de clôture gardé mais **caché si connecté** ; footer sans liens auth.

### État au 2026-09-04 (HEAD `growthos-web` = `8e3f8b4`)

**Phase 1 — CRUD comptes / stratégies / scripts : CODÉ, buildé, lint+tsc OK. Pas encore testé navigateur** (extension Claude-in-Chrome non connectée cette session). Commit `af42d02`. Livré :
- **Primitives** : `src/lib/org.ts` (`requireOrg()` → org courante = 1re appartenance la plus ancienne + `orgName` + `role` + `userId` ; helpers `canManageAccounts` = owner/strategist, `canManageContent` = +editor, `isOwner`). `src/components/ui/form.tsx` (`Field`, `TextInput`/`TextArea`/`Select`, `SubmitButton` via `useFormStatus`, `FormError`, export `fieldClass`). `src/components/ui/badge.tsx` (`Badge` + maps `CONTENT_STATUS`/`ACCOUNT_STATUS`). `PageHeader.description` accepte un `ReactNode`.
- **Comptes** : liste cliquable (compte contenus + badge stratégie), `/accounts/new`, `/accounts/[id]` (détail : méta + carte stratégie + contenus rattachés + zone dangereuse), `/accounts/[id]/edit`. Actions dans `accounts/actions.ts` (`createAccount`/`updateAccount`/`deleteAccount` — gérées par RLS, gating rôle en plus ; gère 23505 handle dupliqué). Suppression = bouton avec confirmation inline (pas de `window.confirm`).
- **Stratégie** (1:1 compte) : `/accounts/[id]/strategy`, `saveStrategy` = **upsert on `account_id`**. `objectives`/`audience` stockés `{ notes: string }`, `priority_formats` = `string[]` (split virgule/newline, max 12), `maturity_score` clampé 0-100.
- **Scripts** (`content_items`) : `/content/new` (+ `?account=<id>` pré-rempli), `/content/[id]`, `/content/[id]/edit`. Éditeur de blocs client (`blocks-editor.tsx` : rôle hook/point/cta + textarea, add/remove/monter/descendre, sérialisé en hidden `blocks_json`). `content/actions.ts` `buildScript()` construit le JSON **au schéma attendu par `engine/script.load_script`** (`title, niche, account`=handle, `organization`=nom, `platform, aspect_ratio, cta, hashtags[], blocks[]`) et le pose dans `content_items.script`. Statut = `idea` si 0 bloc sinon `script` ; `updateScript` ne rétrograde jamais un contenu déjà `video`/`quality_check`/`published`/`queued`/`generating`.
- Command palette : + « Nouveau script » / « Nouveau compte ». Dashboard : liens « Nouveau script » → `/content/new`.

Note schéma : `content_items.status` sur le projet hébergé n'accepte **toujours pas** `queued`/`generating` (check = idea/script/video/quality_check/published/failed) → migration Phase 2 encore à faire. Données hébergées au 2026-09-04 : org « GrowthOS Dogfooding » (1 compte, 1 contenu, owner `sdaiautomation@gmail.com`), org « Test Dogfood — workspace » (vide).

### Phase 2 — file de jobs + worker.py : CODÉE le 2026-09-04, PAS TESTÉE end-to-end (pas d'appel ElevenLabs réel fait cette session)

`growthos-web` (`master` = `9359b14`) + `AiAddicts` (`growthos/mvp` = `05042ed`). Migration `20260904090000_content_item_job_queue` **déjà appliquée** sur le projet hébergé (via MCP Supabase) : `content_items.status` accepte `queued`/`generating` en plus des statuts existants, + colonnes `error` (text) et `requested_by` (uuid → profiles). `database.types.ts` régénéré en conséquence.

Flux : front insère/passe un `content_item` en `status='queued'` (le script JSON est déjà dedans, au schéma `engine/script.load_script`) → `worker.py` (nouveau, racine de `AiAddicts/growthos/`) poll par batch de 1 (`repo.claim_queued_item()`, update conditionné au statut `queued` pour rester correct si deux workers tournent), génère via `engine/assembler.run_for_content_item()` (nouveau — réutilise `_generate()` extrait de `run()`, mais met à jour la ligne `content_items` existante au lieu d'en créer une : pas de `get_or_create` organisation/compte), remet `status='video'` + `video_url`, ou `status='failed'` + `error` sur exception. `python worker.py [--interval N] [--once]`.

Front : bouton « Générer la vidéo » sur `/content/[id]` (`content/[id]/generate-section.tsx`) visible si `status` = `script`/`failed` (refuse si 0 bloc). Pendant `queued`/`generating` : carte d'attente qui s'auto-rafraîchit (`router.refresh()` toutes les 4s — **pas de Realtime configuré exprès**, `supabase_realtime` n'a aucune table publiée sur ce projet ; le polling suffit à l'échelle dogfooding, à reconsidérer si plusieurs utilisateurs simultanés). `video_url` affiché en lien cliquable seulement s'il commence par `http` — sinon (chemin local de la machine qui a fait tourner `worker.py`) affiché en texte : **pas de stockage/upload de la vidéo rendue**, c'est le prochain trou à combler si on veut que d'autres que l'opérateur du worker voient la vidéo.

**Smoke test bout-en-bout : FAIT et réussi (2026-09-04)**, directement en base (pas via l'UI, extension navigateur toujours indisponible) : content_item test inséré en `status='queued'` sur le compte `test-account-01` (org GrowthOS Dogfooding), `python worker.py --once` exécuté réellement (vrai appel ElevenLabs + ffmpeg). Résultat : `status='video'`, `video_url` renseigné, `error` null, `voice_id` résolu (`IHngRooVccHyPqB4uQkG` via la niche `coach-business`), fichiers produits corrects (2 mp3 + full.wav + mp4 64 Ko + caption.txt + checklist.md avec le bon `content_item_id`). Nettoyé après coup (ligne supprimée, dossier `output/test-account-01-smoke-test-worker-phase-2/` effacé — `output/` est gitignore, aucun commit à défaire). **Le chemin worker.py → assembler.run_for_content_item() → repo est donc validé de bout en bout.** Reste non testé : le déclenchement depuis l'UI elle-même (bouton « Générer »), bloqué par l'extension navigateur.

### Publication + Analytics (2026-09-04, `d948c84`) — CODÉ, pas testé navigateur

Équivalent front de `log_metrics.py` : `content/actions.ts` `markPublished()` (video/quality_check → published, `published_at`=now) et `logPerformance()` (insert `content_performance`, refuse si aucune métrique renseignée). Sur `/content/[id]` : `publication-section.tsx` — carte « Marquer comme publié » puis, une fois publié, formulaire de relevé (vues/rétention/likes/commentaires/partages/abonnés/leads) + historique repliable (replié par défaut si >3 relevés).

`/analytics` remplace le placeholder « Bientôt » (nav dé-badgée `soon`) : KPIs (contenus publiés, vues cumulées, rétention moyenne, engagement cumulé, leads) + table « Top performances » (dernier relevé par contenu publié, triée par vues, lien vers le détail). Recommandations IA toujours explicitement hors scope — pas de décision produit prise sur ce qui les générerait.

**Fix flux illisible (2026-09-04, `16022fd`)** : signalé par l'utilisateur (« je ne vois pas les boutons ») en testant lui-même sur `localhost:3210`, sans navigateur piloté par Claude. Cause confirmée : un script créé sans blocs reste en `status='idea'`, et `generate-section.tsx` retournait `null` pour ce statut — aucune carte, aucune explication. Corrigé : carte explicite « Pas encore de script » + lien vers l'édition. Ajouté en prime `pipeline-steps.tsx` — repère de progression (Idée → Script → Vidéo générée → Publié) toujours visible en haut de `/content/[id]`, marque « en cours » / « échec » selon le statut. Utile à retenir : **l'utilisateur peut et sait tester lui-même** l'app en local pendant que l'extension navigateur reste indisponible — ne pas bloquer dessus, lui donner l'URL + le parcours suffit à faire remonter de vrais retours.

**Fix affordance listes (2026-09-04, `a02aeb5`)** : signalé juste après (« je ne sais rien faire avec le contenu, ni éditer, ni supprimer, rien »). Cause : sur `/accounts` et `/content`, seul le texte du titre (lien accent) menait à la fiche détail (où sont Modifier/Supprimer) — le reste de la ligne n'avait ni curseur ni icône le suggérant. Corrigé avec `ui/clickable-row.tsx` : toute la `<tr>` devient cliquable (`cursor-pointer`, navigation au clic n'importe où sur la ligne) + chevron en fin de ligne comme repère constant. Appliqué aux deux tableaux. **Pattern à réutiliser** pour toute future liste de ce genre plutôt que de refaire des `<tr>` planes.

**Fix crash runtime (2026-09-04, `f57c72a`)** : le fix précédent avait introduit `onClick={stopPropagation}` sur les `<Link>` de titre dans `accounts/page.tsx`/`content/page.tsx` — ce sont des Server Components (async, pas de `"use client"`), et Next.js 16 interdit de passer un handler d'événement à un composant depuis un Server Component (« Event handlers cannot be passed to Client Component props »). Retiré : `ClickableRow` (Client Component) gère déjà la navigation, pas besoin du stopPropagation. **Piège à retenir** : ne jamais passer de prop fonction (`onClick`, `onChange`, …) à un composant enfant depuis un fichier sans `"use client"` en tête, même si le composant cible est lui-même client — grep `onClick=\{` et vérifier le fichier appelant avant de committer si un doute.

**Confirmation que le flux marche en vrai pour l'utilisateur** : en traitant la file le 2026-09-04, `worker.py --once` est tombé sur un content_item `L'erreur de prospection N°2` (`requested_by` = l'utilisateur, créé ~13:23, statut `queued`) — **il a donc réussi, seul, à créer un compte/script et cliquer Générer depuis l'UI réelle**, sans que Claude pilote le navigateur. Traité avec succès (status → `video`). Bon signal que les fix successifs (statut idea, lignes cliquables, crash RSC) ont débloqué l'usage réel.

**Stockage vidéo (Supabase Storage) : FAIT, voir [[growthos-known-issues]]** — `video_url` est maintenant une vraie URL publique. Le rendu conditionnel déjà en place dans `content/[id]/page.tsx` (lien cliquable si `video_url` commence par `http`, sinon texte brut) marche donc directement, aucun changement front nécessaire.

### Prochaine session
1. **Tester au navigateur** (Claude ou l'utilisateur) : Phase 1 (CRUD), affordance des listes, bouton Générer, marquer publié + logger des métriques, page Analytics, le repère de progression, le lien vidéo maintenant cliquable. Extension Claude-in-Chrome toujours pas connectée malgré install + tentatives multiples.
2. Débloquer Google OAuth (config user Google Cloud) + tester.
3. Éventuellement passer « Confirm email » OFF (setting Auth Supabase — demander avant).
4. Stockage de la vidéo rendue (Supabase Storage ?) pour que `video_url` soit une vraie URL partageable — actuellement un chemin local à la machine du worker.
5. Boucle de recommandations IA (table `recommendations`/`insights` existe, rien ne l'alimente) — décision produit à prendre (quel modèle, quel déclencheur) avant de coder.

Phase suivante : 3 = quality gate + recommandations.

Pipeline Python : voir [[active-project-growthos]]. Périmètre produit cible : voir [[blotato-product-reference]].
