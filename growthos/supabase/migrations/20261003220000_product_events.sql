-- Lot L5 (audit bible 2026-10-03) : instrumentation produit.
--
-- Avant : aucune table d'événements. `generation_cost_report` est ÉCRASÉ à
-- chaque run, donc le coût des essais successifs d'une même vidéo se perdait
-- et « coût par vidéo satisfaisante » ne pouvait pas se calculer.
--
-- Les événements sont écrits par le worker (service_role) et par le web
-- (membre de l'organisation, pour ses propres événements). Ils ne sont PAS
-- lisibles via l'API : analyse en éditeur SQL / service_role uniquement.

alter table public.organizations
  add column if not exists is_internal boolean not null default false;
comment on column public.organizations.is_internal is
  'Espace interne (dogfooding, tests) : exclu des chiffres clients dans video_satisfaction_summary.';

create table if not exists public.product_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  content_item_id uuid references public.content_items(id) on delete cascade,
  user_id uuid,
  event text not null check (event in (
    'generation_started', 'generation_completed', 'generation_failed',
    'video_exported', 'video_published', 'video_declared_satisfied'
  )),
  props jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists product_events_item_idx
  on public.product_events (content_item_id, created_at);
create index if not exists product_events_org_idx
  on public.product_events (organization_id, created_at);

alter table public.product_events enable row level security;

-- Écriture seule : un membre ne peut insérer que pour son organisation et en
-- son propre nom. Aucune policy de lecture : l'API ne renvoie rien.
create policy "product_events_member_insert" on public.product_events for insert
  to authenticated
  with check (
    organization_id in (select internal.current_user_org_ids())
    and (user_id is null or user_id = auth.uid())
    and event in ('video_exported', 'video_published', 'video_declared_satisfied')
  );

revoke all on table public.product_events from anon, authenticated;
grant insert on table public.product_events to authenticated;
grant all on table public.product_events to service_role;

-- Une ligne par vidéo : essais, coût cumulé, moment où elle devient
-- « satisfaisante » (premier export, publication ou déclaration).
create or replace view public.video_satisfaction
with (security_invoker = true) as
select
  ci.id as content_item_id,
  o.id as organization_id,
  o.is_internal,
  count(*) filter (where e.event = 'generation_completed') as completed_runs,
  count(*) filter (where e.event = 'generation_failed') as failed_runs,
  coalesce(sum((e.props->>'cost_usd')::numeric)
    filter (where e.event in ('generation_completed', 'generation_failed')), 0) as total_cost_usd,
  min(e.created_at) filter (where e.event = 'generation_started') as first_started_at,
  min(e.created_at) filter (where e.event in
    ('video_exported', 'video_published', 'video_declared_satisfied')) as satisfied_at
from public.content_items ci
join public.accounts a on a.id = ci.account_id
join public.organizations o on o.id = a.organization_id
left join public.product_events e on e.content_item_id = ci.id
group by ci.id, o.id, o.is_internal;

-- Le chiffre de la bible : coût total des essais ÷ vidéos satisfaisantes,
-- médiane et P90, comptes internes séparés des clients.
create or replace view public.video_satisfaction_summary
with (security_invoker = true) as
select
  is_internal,
  count(*) as satisfying_videos,
  round(sum(total_cost_usd) / nullif(count(*), 0), 4) as cost_per_satisfying_video_usd,
  round((percentile_cont(0.5) within group (order by total_cost_usd))::numeric, 4) as median_cost_usd,
  round((percentile_cont(0.9) within group (order by total_cost_usd))::numeric, 4) as p90_cost_usd,
  percentile_cont(0.5) within group (order by completed_runs) as median_runs,
  percentile_cont(0.9) within group (order by completed_runs) as p90_runs,
  round((percentile_cont(0.5) within group (
    order by extract(epoch from (satisfied_at - first_started_at)) / 60))::numeric, 1) as median_minutes_to_satisfying
from public.video_satisfaction
where satisfied_at is not null and first_started_at is not null
group by is_internal;

revoke all on public.video_satisfaction, public.video_satisfaction_summary from anon, authenticated;
grant select on public.video_satisfaction, public.video_satisfaction_summary to service_role;
