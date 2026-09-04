---
name: growthos-web-frontend
description: Faceloop (ex-GrowthOS) frontend — separate repo growthos-web, Next.js + Supabase, started 2026-09-03, deployed to Vercel 2026-09-04
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

### Déploiement Vercel + rebrand Faceloop (2026-09-04, soir)

**Déployé en production** : https://growthos-web-jade.vercel.app (projet Vercel `growthos-web`, équipe `sdaiautomations-projects`, `prj_mG4NWiauIA7NhLtU3Heil0358LQm`). Trajet chaotique — à retenir pour la prochaine fois :
- `create_git_project` (MCP Vercel) a échoué au premier essai (repo privé, app GitHub Vercel pas encore autorisée sur `growthos-web` — l'utilisateur a dû l'ajouter manuellement dans github.com/settings/installations). Après ça, le connecteur Vercel est resté **incohérent toute la session** (`list_projects`/`get_project` renvoient 404 alors que `create_git_project` dit 409 « existe déjà », `list_deployments` 403) — jamais fiable pour lire l'état, seul `curl` direct sur l'URL publique a donné des réponses fiables.
- Cause du 500 initial : variables d'env `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` — le préfixe `NEXT_PUBLIC_` n'est pas optionnel (l'utilisateur l'a d'abord retiré en pensant qu'il gênait, "Vercel veut pas le public"). Type de variable : **Config**, jamais **Secret** (une var `NEXT_PUBLIC_*` finit de toute façon dans le bundle client, "Secret" n'a pas de sens dessus).
- Cause du 500 persistant après correction : **build cache réutilisé** — le Middleware (Edge runtime, bundle compilé séparément) gardait l'ancienne version sans les vars même après un redeploy classique. Fix : Deployments → (...) → Redeploy → **décocher "Use existing Build Cache"**.
- Le webhook Git auto-deploy a été instable (des push n'ont pas déclenché de build) puis s'est remis à marcher tout seul après un "Promote to Production" manuel — pas d'explication claire, à surveiller sur les prochains push.
- **Toujours pas de domaine custom connecté** — juste l'URL Vercel par défaut.

**Rebrand GrowthOS → Faceloop (`4c2ce31`)** : nom de domaine choisi par l'utilisateur = **faceloop.app** (growthos.* trop pris). Renommé partout dans le texte visible (wordmark "F", titres de pages, landing, CGU/Confidentialité, design-system.md). Volontairement **pas renommé** : repo GitHub / `package.json` / projet Vercel (`growthos-web`) — risque de re-casser la liaison Git déjà fragile ce soir. Nom de l'org Supabase de dogfooding (« GrowthOS Dogfooding ») pas touché non plus (donnée pipeline, pas une marque affichée). Vérifié en ligne après déploiement : titre, eyebrow "Faceless Content OS", wordmark F, liens CGU/Confidentialité — tous présents sur le site en prod.

**Reste à faire pour le domaine** : l'utilisateur doit acheter `faceloop.app` (registrar au choix), puis l'ajouter dans Vercel → Project Settings → Domains → Add. Pas fait cette session.

### Landing : section Tarifs + prix réels (2026-09-04, `02b1693` → `ef3a7a2`)

`pricing-section.tsx` (client component, juste après « Comment ça marche ») : 3 plans Starter/Pro/Business, toggle Mensuel/Annuel (-20%), badge « Populaire » sur Pro. Prix choisis après recherche marché réelle (pas inventés) :
- **Starter 19€/mois (15€ annuel)** — 1 compte, 10 vidéos/mois. Aligné sur l'entrée de gamme marché (FacelessReels.com 19$, Faceless.so 24$).
- **Pro 59€/mois (47€ annuel)** — 5 comptes, **150 vidéos/mois** (pas « illimité » — décision utilisateur, aucun concurrent réel n'utilise ce mot, tous affichent un chiffre), voix premium + clonage, analytics avancés, support prioritaire. Entre Growth (49$) et Influencer (107$) de Faceless.so.
- **Business** : sur devis (« Nous contacter »), comptes illimités, API, onboarding dédié.

Coût variable ElevenLabs mesuré/estimé : **~0,20€/vidéo** (~1200 caractères de voix off, ~0,00017€/caractère, stable entre paliers ElevenLabs $6→$990/mois). Marge visée : ~85%+ sur Starter, ~55-65% sur Pro à usage réaliste (100 vidéos/mois). **Pas encore de garde-fou côté backend** pour faire respecter le plafond de 150 vidéos/mois sur Pro — juste affiché en façade pour l'instant, à implémenter avant lancement commercial réel (limite/quota par organisation).

### Facturation Stripe (2026-09-04, `555b37d` growthos-web / `80a6aa8` AiAddicts)

**Checkout réel + webhook + page Facturation, vérifié en réel de bout en bout.** Compte Stripe de l'utilisateur, clé test `sk_test_51UC2xP2Wu...` fournie en chat — **⚠️ une clé LIVE (`sk_live_...`) du même compte a aussi transité dans le chat par erreur avant que l'utilisateur ne se corrige** ; il doit la régénérer (dashboard.stripe.com/apikeys → Roll key) dès qu'il a un instant, pas fait pendant la session.

- **Migration** `organizations.plan` réaligné `starter/pro/business` (l'ancien `starter/growth/agency/agency_pro` ne correspondait à rien d'affiché). + colonnes `stripe_customer_id`/`stripe_subscription_id`/`stripe_price_id`/`subscription_status`.
- **Durcissement trouvé en cours de route** : la policy `organizations_owner_update` existante autorisait un owner à modifier N'IMPORTE QUELLE colonne de sa ligne (RLS ne restreint que les lignes, pas les colonnes) — un owner pouvait donc déjà se passer en plan payant via l'API REST Supabase directe, en contournant complètement l'app. Corrigé par `GRANT UPDATE (name) ON organizations TO authenticated` (+ `REVOKE UPDATE`) — authenticated ne peut plus modifier que `name`, tout le reste (plan, stripe_*) ne bouge que via le webhook en service_role.
- **Stripe** : Products/Prices créés via `growthos-web/scripts/stripe-setup.mjs` (idempotent, lookup_key stable test/live, refuse de tourner avec une clé live). `tax_code SaaS B2B (txcd_10103000)` **requis** sur chaque Product — sans ça la création de Checkout Session échoue (Managed Payments activé par défaut sur ce compte Stripe). Repéré en testant en réel, pas en lisant la doc.
- **Checkout** (`settings/actions.ts`) : ne pré-crée jamais de client Stripe ni n'écrit `stripe_customer_id` depuis l'action utilisateur (session RLS-scopée) — Stripe crée/lie le client à la volée via `client_reference_id`, seul le webhook persiste. Évite d'avoir besoin d'un droit d'écriture élargi.
- **Webhook** (`api/webhooks/stripe/route.ts`, `lib/supabase/service.ts` nouveau client service_role) : ajouté à `PUBLIC_PATHS` (scopé `/api/webhooks`, pas tout `/api`) puisqu'un appel Stripe n'a pas de session Supabase — l'authenticité vient de la vérification HMAC, testée : payload non signé -> 400, les 3 events (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`) envoyés avec une vraie signature vers l'app en local ont correctement fait transiter une org réelle `starter -> pro (active) -> starter (canceled)`. `scripts/test-webhook-local.mjs` conservé pour retester (construit et signe de vrais payloads HMAC, aucun besoin du Stripe CLI).
- **Page Facturation** (`settings/billing-section.tsx`) : mêmes prix que la landing (19€/59€, -20% annuel), badge "Plan actuel", bouton portail client Stripe si déjà abonné.

**Pas fait / à reprendre** :
1. **Vercel** : `STRIPE_SECRET_KEY` (test), `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` pas encore ajoutées en prod — le webhook réel (`https://www.faceloop.app/api/webhooks/stripe`, endpoint déjà créé côté Stripe, id `we_1UC4Lo2WuBCHDAgtxeyQIPhc`) ne fonctionnera qu'une fois ces 3 variables posées + un redeploy **sans cache** (piège déjà rencontré ce soir avec les variables Supabase — le Middleware garde l'ancien build sinon).
2. Quota d'usage (150 vidéos/mois Pro, 10 Starter) toujours pas fait respecter côté génération — juste affiché en façade.
3. Repasser en mode live (vraies clés) uniquement après avoir testé un vrai parcours de paiement complet (carte test 4242 4242 4242 4242) une fois déployé.

### En-têtes de sécurité + middleware bloquait robots.txt/sitemap.xml (2026-09-04, `47863bf`)

Audit fourni par l'utilisateur (headers manquants + middleware trop large). Vérifié le vrai bug avant de corriger : la prod redirigeait bien `/robots.txt` vers `/login` (307). Deux fichiers modifiés :
- `next.config.ts` : CSP + X-Frame-Options/X-Content-Type-Options/Referrer-Policy/Permissions-Policy/HSTS renforcé + `poweredByHeader: false`. **CSP statique (pas de nonce)** — le nonce-based CSP officiellement recommandé par Next.js pour l'App Router force TOUTES les pages en rendu dynamique (plus de statique pour landing/login/terms/privacy), écarté délibérément pour ce coût de perf. `'unsafe-inline'` sur script-src/style-src requis par les scripts inline que l'App Router injecte lui-même (hydratation RSC) — `script-src` reste `'self'`, aucun domaine tiers chargeable. `connect-src` limité à Supabase (seul domaine appelé côté navigateur, vérifié dans le code).
- `lib/supabase/middleware.ts` : `PUBLIC_PATHS` étendu à `/robots.txt`, `/sitemap.xml`, `/manifest.json`, `/manifest.webmanifest` — **aucun de ces fichiers n'existe encore** (pas de `src/app/robots.ts`/`sitemap.ts`, juste le blocage corrigé en prévision). `/favicon.ico` passe par un mécanisme différent (exclusion dans le `matcher` de `proxy.ts`, pas PUBLIC_PATHS) — les deux mécanismes coexistaient déjà avant, juste harmonisés/documentés.

Vérifié en prod après déploiement : les 6 headers présents sur `/`, `X-Powered-By` absent, `/robots.txt` → 404 (plus 307 vers /login), `/dashboard` → toujours 307 (protection intacte), `/auth/confirm` + `/auth/callback` → toujours 307 vers /login?error (pas cassés). Build : toutes les pages statiques le restent (pas de passage forcé en dynamique).

**Suite logique pas faite** : créer un vrai `robots.txt`/`sitemap.xml` (`src/app/robots.ts`/`sitemap.ts`, convention Next) — le fix de ce soir empêche juste le blocage, ne crée pas le contenu. À faire si le référencement SEO devient une priorité.

### Revue de sécurité (2026-09-04, `d4980a0`)

`/security-review` sur `AiAddicts` (branche `growthos/mvp`) ne couvre que `growthos/` (pipeline Python, repo différent de `growthos-web`) — 0 finding à confiance ≥8. Relu `growthos-web` à la main en plus (hors périmètre mécanique du skill mais dans l'esprit de la demande de l'utilisateur) : **open redirect trouvé et corrigé** — `login/actions.ts` faisait `redirect(next.startsWith("/") ? next : "/dashboard")`, or `"//evil.com"` passe ce test (URL protocol-relative → le navigateur résout vers `https://evil.com`). `lib/safe-redirect-target.ts` (nouveau, exclut aussi le préfixe `//`) appliqué aux 3 endroits qui acceptent un `next` (`login/actions.ts` — la seule vraiment exploitable ; `auth/callback` et `auth/confirm` préfixaient déjà `${origin}` donc étaient déjà sûrs, corrigés par cohérence).

### Bug connexion → redirige vers localhost (2026-09-04 diagnostiqué → 2026-09-05 CORRIGÉ par l'utilisateur)

Signalé par l'utilisateur le 2026-09-04 : en essayant de se connecter / confirmer son email sur le site en prod, il était renvoyé vers `localhost`. Pas un bug de code — `emailRedirectTo` est déjà construit dynamiquement depuis l'origine de la requête. Cause : config du dashboard Supabase Auth (Site URL / Redirect URLs encore sur localhost). **Corrigé par l'utilisateur le 2026-09-05** (Site URL + Redirect URLs mis à jour côté dashboard). Pas re-testé par Claude (extension navigateur toujours indisponible) — à confirmer par un vrai essai de connexion si un doute survient.

### Domaine + variables Vercel (2026-09-05)

**`faceloop.app` connecté** — vérifié en direct : `https://faceloop.app/` redirige (307) vers `https://www.faceloop.app/` en HTTP 200, avec les en-têtes de sécurité (CSP/HSTS/X-Frame-Options) présents dessus → c'est bien le bon déploiement qui répond sur le domaine custom, pas un résidu de l'ancienne URL `growthos-web-jade.vercel.app`.

**Variables Stripe/service-role posées sur Vercel** — vérifié indirectement : `POST /api/webhooks/stripe` sans signature valide renvoie `400` (vérification de signature qui s'exécute correctement) plutôt qu'un `500` (crash au démarrage si `STRIPE_WEBHOOK_SECRET`/`STRIPE_SECRET_KEY` manquaient). Cohérent avec des variables bien chargées. **Pas encore vérifié à 100%** : la confirmation définitive viendra du premier vrai paiement test bout-en-bout (checkout → webhook → org mise à jour en base) — à faire à l'occasion.

**Clé Stripe live rotée par l'utilisateur (2026-09-05)** — la `sk_live_51UC2xP2Wu...` exposée par erreur dans le chat le 2026-09-04 a été régénérée (dashboard.stripe.com/apikeys → Roll key). L'ancienne clé est donc invalide si quelqu'un l'avait récupérée. Pas de changement pour le fonctionnement actuel de l'app : elle tourne toujours en mode test (`sk_test_...`), la clé live n'est utilisée nulle part dans le code pour l'instant — cette rotation ne sera à répercuter dans `.env.local`/Vercel qu'au moment de vraiment passer l'app en mode live (facturation réelle), pas avant.

### Prochaine session — TODO propre (mise à jour 2026-09-05)

Plus aucun point bloquant connu. Priorité normale, dans un ordre logique :
1. **Test bout-en-bout réel** : inscription/connexion (vérifier que le fix Supabase Auth marche vraiment), CRUD comptes/scripts, bouton Générer, marquer publié + logger des métriques, page Analytics, dark mode, **parcours Stripe complet avec carte test 4242 4242 4242 4242** (confirme définitivement les vars d'env + le webhook). Extension Claude-in-Chrome toujours pas connectée malgré install + tentatives multiples.
2. Débloquer Google OAuth (config user Google Cloud, `redirect_uri_mismatch` — ancien point, statut non reconfirmé) + tester.
3. **Quota d'usage** (150 vidéos/mois Pro, 10 Starter) toujours pas fait respecter techniquement côté génération — juste affiché en façade. À implémenter avant tout lancement commercial réel.
4. `robots.txt`/`sitemap.xml` réels (`src/app/robots.ts`/`sitemap.ts`) — le fix middleware empêche juste qu'ils cassent une fois créés, ne les crée pas. Si le SEO devient une priorité.
5. Boucle de recommandations IA (table `recommendations`/`insights` existe, rien ne l'alimente) — décision produit à prendre (quel modèle, quel déclencheur) avant de coder.
6. **TikTok Content Posting API** : prérequis (CGU/Confidentialité + déploiement public) réunis. Reste : l'utilisateur crée le compte développeur TikTok + enregistre l'app, puis Claude code le flux OAuth (Login Kit) + l'appel de publication (schéma `account_oauth_tokens` déjà en place côté DB).
7. **Avant tout vrai lancement commercial** : repasser en mode live (vraies clés Stripe) seulement après avoir testé un vrai parcours de paiement complet en test, et régénérer/poser la nouvelle clé live rotée dans Vercel à ce moment-là (pas avant).

Phase suivante (pipeline) : 3 = quality gate + recommandations.

**État des repos au 2026-09-04 fin de soirée** : les deux repos (`growthos-web` sur `master`, `AiAddicts` sur `growthos/mvp`) sont **propres et entièrement poussés** — rien en attente de commit ni de push.

Pipeline Python : voir [[active-project-growthos]]. Périmètre produit cible : voir [[blotato-product-reference]].
