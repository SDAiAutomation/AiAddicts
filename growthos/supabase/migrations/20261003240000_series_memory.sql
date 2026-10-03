-- Lot L4 (audit bible 2026-10-03) : mémoire de série minimale.
--
-- Avant : une série ne retenait que sa prémisse et les 5 derniers titres ;
-- les personnages étaient réinventés à chaque épisode (apparence qui change)
-- et rien n'empêchait de révéler deux fois le même secret.
--
-- Deux tables rattachées à `series` : fiches personnages et faits canon. Chaque
-- ligne a un statut. Seul ce qui est `approved` entre dans la génération ;
-- l'IA ne fait que PROPOSER (`proposed`), l'utilisateur approuve ou rejette.
-- Une ligne `rejected` est conservée pour ne pas être reproposée.

create table if not exists public.series_characters (
  id uuid primary key default gen_random_uuid(),
  series_id uuid not null references public.series(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  description text not null check (char_length(description) between 1 and 600),
  negative text check (negative is null or char_length(negative) <= 300),
  status text not null default 'proposed' check (status in ('proposed', 'approved', 'rejected')),
  source text not null default 'ai' check (source in ('ai', 'manual')),
  first_episode integer check (first_episode is null or first_episode >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists series_characters_name_idx
  on public.series_characters (series_id, lower(name));

create table if not exists public.series_canon_facts (
  id uuid primary key default gen_random_uuid(),
  series_id uuid not null references public.series(id) on delete cascade,
  fact text not null check (char_length(fact) between 1 and 400),
  kind text not null default 'event' check (kind in ('secret', 'event', 'relationship', 'rule')),
  status text not null default 'proposed' check (status in ('proposed', 'approved', 'rejected')),
  source text not null default 'ai' check (source in ('ai', 'manual')),
  episode_number integer check (episode_number is null or episode_number >= 1),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists series_canon_facts_series_idx
  on public.series_canon_facts (series_id, status);

alter table public.series_characters enable row level security;
alter table public.series_canon_facts enable row level security;

-- Lecture : membres de l'organisation propriétaire de la série.
-- Écriture : owner / strategist / editor (comme les contenus).
create policy "series_characters_member_select" on public.series_characters for select
  using (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.account_organization_id(s.account_id) in (select internal.current_user_org_ids())
  ));
create policy "series_characters_editor_write" on public.series_characters for all
  using (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.has_org_role(internal.account_organization_id(s.account_id), array['owner','strategist','editor'])
  ))
  with check (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.has_org_role(internal.account_organization_id(s.account_id), array['owner','strategist','editor'])
  ));

create policy "series_canon_facts_member_select" on public.series_canon_facts for select
  using (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.account_organization_id(s.account_id) in (select internal.current_user_org_ids())
  ));
create policy "series_canon_facts_editor_write" on public.series_canon_facts for all
  using (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.has_org_role(internal.account_organization_id(s.account_id), array['owner','strategist','editor'])
  ))
  with check (exists (
    select 1 from public.series s
    where s.id = series_id
      and internal.has_org_role(internal.account_organization_id(s.account_id), array['owner','strategist','editor'])
  ));

revoke all on table public.series_characters, public.series_canon_facts from anon;
grant select, insert, update, delete on table public.series_characters, public.series_canon_facts to authenticated;
grant all on table public.series_characters, public.series_canon_facts to service_role;
