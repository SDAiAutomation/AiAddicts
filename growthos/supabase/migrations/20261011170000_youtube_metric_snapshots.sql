-- Provenance des mesures YouTube : une ligne par video et par jour UTC, ecrite uniquement par le
-- collecteur (service_role) depuis /api/cron/youtube-metrics de growthos-web, derriere
-- ENABLE_YOUTUBE_METRICS_PROVENANCE_WRITE (eteint par defaut). content_performance reste inchange et
-- reste la source lue partout ; cette table ne contient AUCUN historique retro-etiquete.
--
-- Teste sur une branche Supabase jetable (21 controles : isolation entre deux organisations, droits
-- anon / authenticated / service_role, contraintes, idempotence). Voir growthos-web PR #64.
create table if not exists public.youtube_metric_snapshots (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  collected_at timestamptz not null default now(),
  snapshot_day date not null,
  data_api_views bigint check (data_api_views >= 0),
  analytics_subscribers_gained bigint check (analytics_subscribers_gained >= 0),
  analytics_start_date date,
  analytics_end_date date,
  data_api_fetched_at timestamptz,
  analytics_fetched_at timestamptz,
  analytics_status text not null check (analytics_status in ('ok','missing_scope','no_data','error')),
  source text not null default 'youtube_auto_v1'
    check (source = 'youtube_auto_v1'),
  constraint youtube_metric_one_snapshot_per_utc_day unique (content_item_id, snapshot_day),
  constraint youtube_metric_analytics_dates_valid
    check (analytics_start_date is null or analytics_end_date is null
           or analytics_end_date >= analytics_start_date)
);
create index if not exists youtube_metric_snapshots_video_latest_idx
  on public.youtube_metric_snapshots (content_item_id, collected_at desc);
alter table public.youtube_metric_snapshots enable row level security;

-- Lecture pour les membres de l'organisation de la video, ecrite comme content_performance_member_select.
-- Aucun filtre sur accounts.platform (simple etiquette d'affichage). Aucune politique d'ecriture.
drop policy if exists "youtube_metrics_member_read" on public.youtube_metric_snapshots;
create policy "youtube_metrics_member_read"
on public.youtube_metric_snapshots for select to authenticated
using (internal.content_item_organization_id(content_item_id) in (select internal.current_user_org_ids()));
revoke all on table public.youtube_metric_snapshots from anon, authenticated;
grant select on table public.youtube_metric_snapshots to authenticated;
-- Le collecteur recoit explicitement select + insert : il ne depend pas des privileges par defaut du projet
-- (sur une branche Supabase ils ne donnent pas l'ecriture a service_role). En PRODUCTION ces privileges par
-- defaut lui donnent deja tout (update et delete compris) : le grant ajoute des droits, il n'en retire pas.
-- Pour une table append-only, il faudrait ajouter : revoke update, delete on ... from service_role.
grant select, insert on table public.youtube_metric_snapshots to service_role;
comment on table public.youtube_metric_snapshots is
'YouTube API sourced snapshots only. No historical backfill without verified provenance.';
