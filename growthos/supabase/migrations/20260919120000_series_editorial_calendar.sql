-- Calendrier éditorial des séries.
-- Le script est préparé plusieurs jours avant le créneau, reste modifiable,
-- puis la vidéo est rendue à validation ou trois heures avant publication.

alter table public.content_items
  add column scheduled_for timestamptz,
  add column generation_deadline timestamptz,
  add column editorial_status text
    check (editorial_status in ('draft', 'approved', 'locked')),
  add column script_score integer check (script_score between 0 and 100),
  add column score_details jsonb not null default '{}'::jsonb,
  add column script_version integer not null default 1 check (script_version > 0),
  add column video_script_version integer;

create unique index content_items_series_slot_unique
  on public.content_items(series_id, scheduled_for)
  where series_id is not null and scheduled_for is not null;

create index content_items_series_calendar_idx
  on public.content_items(series_id, scheduled_for);

alter table public.content_publication_jobs
  add column scheduled_for timestamptz not null default now();

create index content_publication_jobs_schedule_idx
  on public.content_publication_jobs(scheduled_for, created_at)
  where status = 'pending';

-- La réservation peut désormais porter sur un créneau futur compris dans la
-- fenêtre éditoriale. La comparaison exacte conserve la protection contre les
-- doubles passages concurrents.
create or replace function public.claim_series_run(
  p_series_id uuid,
  p_expected_next_run_at timestamptz,
  p_next_run_at timestamptz
)
returns integer
language sql
security definer
set search_path = public
as $$
  update public.series
  set next_run_at = p_next_run_at,
      last_run_at = now(),
      last_error = null
  where id = p_series_id
    and status = 'active'
    and next_run_at = p_expected_next_run_at
  returning episode_count + 1;
$$;

revoke all on function public.claim_series_run(uuid, timestamptz, timestamptz) from public;
grant execute on function public.claim_series_run(uuid, timestamptz, timestamptz) to service_role;

-- À chaque passage du planner, verrouille et met en file les scripts arrivés
-- à échéance. Un script approuvé est déjà mis en file par l'action web.
create or replace function public.queue_due_series_episodes(p_series_id uuid default null)
returns setof uuid
language sql
security definer
set search_path = public
as $$
  update public.content_items item
  set status = 'queued',
      editorial_status = 'locked',
      error = null,
      updated_at = now()
  from public.series s
  where item.series_id = s.id
    and s.status = 'active'
    and (p_series_id is null or item.series_id = p_series_id)
    and item.status = 'script'
    and item.editorial_status in ('draft', 'approved')
    and item.generation_deadline <= now()
  returning item.id;
$$;

revoke all on function public.queue_due_series_episodes(uuid) from public;
grant execute on function public.queue_due_series_episodes(uuid) to service_role;

-- Toute modification d'un épisode futur invalide son ancien rendu et une
-- éventuelle publication encore en attente. Une vidéo déjà publiée reste
-- immuable : le web bloque également son édition destructrice.
create or replace function public.invalidate_series_episode_on_script_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.series_id is not null
     and old.status <> 'published'
     and old.script is distinct from new.script then
    new.status := 'script';
    new.editorial_status := 'draft';
    new.script_version := old.script_version + 1;
    new.video_script_version := null;
    new.video_url := null;
    new.original_video_url := null;
    new.quality_score := null;
    new.quality_flags := '[]'::jsonb;
    new.error := null;
    delete from public.content_publication_jobs
      where content_item_id = old.id and status <> 'published';
  end if;
  return new;
end;
$$;

revoke all on function public.invalidate_series_episode_on_script_change() from public;

create trigger invalidate_series_episode_before_script_update
  before update of script on public.content_items
  for each row execute function public.invalidate_series_episode_on_script_change();

create or replace function public.record_rendered_script_version()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.status in ('video', 'quality_check') and old.status = 'generating' then
    new.video_script_version := new.script_version;
  end if;
  return new;
end;
$$;

create trigger record_rendered_script_version_before_status_update
  before update of status on public.content_items
  for each row execute function public.record_rendered_script_version();

-- Une vidéo terminée peut attendre plusieurs jours avant son heure réelle de
-- publication. Les contenus manuels, sans scheduled_for, restent immédiats.
create or replace function public.queue_series_publication()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  config record;
  target_platform text;
begin
  if new.series_id is null
     or new.status not in ('video', 'quality_check')
     or old.status = new.status
     or old.status = 'published'
     or new.video_url is null
     or new.video_url !~ '^https?://' then
    return new;
  end if;

  select auto_publish_mode, auto_publish_platforms
    into config from public.series where id = new.series_id;
  if not found or config.auto_publish_mode = 'off' then return new; end if;
  if config.auto_publish_mode = 'quality'
     and (new.status <> 'video' or new.quality_score is null or new.quality_score < 70) then
    return new;
  end if;

  foreach target_platform in array config.auto_publish_platforms loop
    if exists (
      select 1 from public.account_oauth_tokens token
      where token.account_id = new.account_id
        and token.platform = target_platform
        and token.status = 'connected'
    ) then
      insert into public.content_publication_jobs (content_item_id, platform, scheduled_for)
      values (new.id, target_platform, coalesce(new.scheduled_for, now()))
      on conflict (content_item_id, platform) do update
        set scheduled_for = excluded.scheduled_for,
            status = case
              when public.content_publication_jobs.status = 'published' then 'published'
              else 'pending'
            end,
            error = null;
    end if;
  end loop;
  return new;
end;
$$;

create or replace function public.claim_content_publication_job()
returns setof public.content_publication_jobs
language sql
security definer
set search_path = public
as $$
  update public.content_publication_jobs
  set status = 'needs_review',
      error = 'Envoi interrompu : vérifie YouTube avant de relancer manuellement.',
      completed_at = now()
  where status = 'processing' and started_at < now() - interval '15 minutes';

  update public.content_publication_jobs job
  set status = 'processing',
      attempts = job.attempts + 1,
      started_at = now(),
      error = null
  where job.id = (
    select pending.id
    from public.content_publication_jobs pending
    where pending.status = 'pending'
      and pending.scheduled_for <= now()
    order by pending.scheduled_for, pending.created_at, pending.id
    for update skip locked
    limit 1
  )
  returning job.*;
$$;

revoke all on function public.claim_content_publication_job() from public;
grant execute on function public.claim_content_publication_job() to service_role;
