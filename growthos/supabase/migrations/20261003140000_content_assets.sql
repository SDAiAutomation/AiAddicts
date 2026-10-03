-- Lot L1 (audit bible 2026-10-03) : manifeste d'actifs réutilisables.
--
-- Le worker tourne sur un runner éphémère : voix et images déjà payées étaient
-- perdues entre deux passages, donc corriger un mot coûtait une régénération
-- complète. Chaque actif payant (voix d'un bloc, image d'une scène) est
-- désormais stocké sous une clé = empreinte de TOUTES ses entrées (texte,
-- voix, prompt final, modèle...). Une correction ne régénère que les actifs
-- dont l'empreinte a changé.
--
-- Accès : service_role uniquement (RLS activé, aucune policy) — le worker
-- lit/écrit, l'interface n'a pas besoin de ces lignes pour l'instant.

create table if not exists public.content_assets (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  kind text not null check (kind in ('voice', 'voice_words', 'image')),
  input_hash text not null check (char_length(input_hash) between 16 and 64),
  storage_path text not null,
  bytes bigint,
  estimated_cost numeric,
  provider text,
  created_at timestamptz not null default now(),
  last_used_at timestamptz not null default now(),
  unique (content_item_id, kind, input_hash)
);

create index if not exists content_assets_last_used_idx
  on public.content_assets (last_used_at);

alter table public.content_assets enable row level security;
revoke all on table public.content_assets from anon, authenticated;
grant all on table public.content_assets to service_role;

-- Bucket privé : les actifs ne sont jamais servis au public.
insert into storage.buckets (id, name, public)
values ('content-assets', 'content-assets', false)
on conflict (id) do nothing;
