---
name: growthos-web-frontend
description: GrowthOS frontend — separate repo growthos-web, Next.js + Supabase, started 2026-09-03
metadata:
  type: project
---

Décidé le 2026-09-03 (réponses AskUserQuestion de l'utilisateur) : **app complète**, **Next.js + Supabase**, **repo dédié séparé**, **auth Supabase activée maintenant**.

Emplacement disque : `C:\Users\user2\Desktop\GrowthOS\growthos-web` (frère de `AiAddicts/`, PAS dans le monorepo). Repo git local initialisé, **pas encore de remote GitHub**. Auteur des commits : `SDAiAutomation <sdaiautomation@gmail.com>` (via `-c`, pas de config globale sur la machine).

Stack : Next.js 16 (App Router, Turbopack), React 19, TS, Tailwind v4, `@supabase/ssr`, `lucide-react`, `cmdk`. Convention Next 16 : `src/proxy.ts` (pas `middleware.ts`) pour la garde de routes.

**Design system** : `docs/design-system.md` (fourni par l'utilisateur 2026-09-03, style Linear/Stripe, anti-AI-slop). Points durs : **light par défaut** (`#F8FAFC`/`#FFFFFF`/`#E2E8F0`/`#0F172A`/`#64748B`), **accent unique `#2563EB`**, dark en opt-in `[data-theme="dark"]` seulement (pas de suivi OS), radius 6/8/12, Lucide (jamais d'emoji), command palette ⌘K obligatoire, tous les états (loading/empty/error/success) sur chaque surface. La 1re version de la Phase 0 était en dark+cyan → refaite (commit `fec9a21`). Tokens dans `src/app/globals.css`, primitives dans `src/components/ui/`, shell dans `src/components/app-shell/`. Voir [[blotato-product-reference]] pour le périmètre produit (style = anti-modèle).

**Architecture génération** : le pipeline Python (ffmpeg/ElevenLabs) ne tourne pas sur Vercel → file de jobs via la DB. Le front insère `content_items` en `status='queued'`, un `worker.py` (à écrire, dans `AiAddicts/growthos/`) poll et lance `assembler.run()` en service_role, le front suit le statut via Realtime. Nécessite 1 migration : ajouter `queued`/`generating` au check `content_items.status` + colonnes `error`, `requested_by`.

Phases : 0 = auth + dashboard (**FAIT ET VÉRIFIÉ end-to-end 2026-09-03**, commit `981ec2d`, repo GitHub `SDAiAutomation/growthos-web` privé, branche `master`) · 1 = CRUD comptes/stratégies/scripts · 2 = file de jobs + worker + bouton Générer · 3 = quality gate + recommandations.

Auth en place : user Supabase `sdaiautomation@gmail.com` (uid `8b5223cb-2e32-44d3-837c-bf5e363be41d`), `profiles` + `organization_members` (owner de « GrowthOS Dogfooding ») créés via `backfill_membership.py`. Login email+mot de passe OK, RLS OK (dashboard affiche bien le compte test + le content_item du premier run).

Pipeline Python : voir [[active-project-growthos]].
