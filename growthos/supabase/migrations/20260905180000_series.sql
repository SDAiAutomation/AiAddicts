-- Séries (contenu récurrent, format anthologie) — comparatif facelessreels.com
-- ("Les Dossiers Interdits - Saison 1", "Next video in 23 hours"). Une série
-- génère automatiquement un nouvel épisode à intervalle régulier : nouveau
-- sujet à chaque fois dans la même niche/format, pas de continuité narrative
-- entre épisodes (décision produit 2026-09-05).

create table series (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  niche_id uuid references niches(id) on delete set null,
  name text not null,
  premise text,
  cadence_hours integer not null default 24 check (cadence_hours > 0),
  visual_style text,
  voice_id text,
  status text not null default 'active' check (status in ('active', 'paused')),
  next_run_at timestamptz not null default now(),
  episode_count integer not null default 0,
  created_at timestamptz not null default now()
);
create index on series (account_id);
create index on series (status, next_run_at);

-- Un content_item peut être un épisode d'une série (généré automatiquement)
-- ou un script normal (series_id null, comportement inchangé).
alter table content_items add column series_id uuid references series(id) on delete set null;
alter table content_items add column episode_number integer;

alter table series enable row level security;

create policy "series_member_select" on series for select
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
-- Écriture réservée à owner/strategist (comme accounts) : une série engage
-- des crédits de façon récurrente sans validation manuelle à chaque fois,
-- une décision plus lourde qu'écrire un script au coup par coup.
create policy "series_write_roles" on series for insert
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
create policy "series_update_roles" on series for update
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
create policy "series_delete_roles" on series for delete
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
