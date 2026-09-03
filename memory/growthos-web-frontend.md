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

**Polish repéré, pas fait** : bouton « Replier » sidebar chevauché par le badge dev Next.js ; contenu dashboard un peu décalé (passer en aligné-gauche vs `max-w-5xl` centré) ; `.gitattributes` sur growthos-web pour le bruit CRLF.

### Prochaine session
1. Débloquer Google OAuth (config user) + tester.
2. Éventuellement passer « Confirm email » OFF.
3. **Phase 1** : CRUD comptes / stratégies / scripts (formulaires, écriture RLS rôles owner/strategist).

Phases suivantes : 2 = file de jobs + `worker.py` + bouton Générer · 3 = quality gate + recommandations.

Pipeline Python : voir [[active-project-growthos]]. Périmètre produit cible : voir [[blotato-product-reference]].
