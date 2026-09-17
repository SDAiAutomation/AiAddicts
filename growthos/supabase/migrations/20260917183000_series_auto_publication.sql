-- Publication automatique volontaire, configurable par série.
-- Les épisodes déjà rendus ne sont pas publiés rétroactivement.
alter table public.series
  add column auto_publish_mode text not null default 'off'
    check (auto_publish_mode in ('off', 'quality', 'all')),
  add column auto_publish_platforms text[] not null default '{}'
    check (auto_publish_platforms <@ array['youtube']::text[]);

alter table public.content_items
  add column youtube_privacy_status text;

create table public.content_publication_jobs (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  platform text not null check (platform = 'youtube'),
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'published', 'failed', 'needs_review')),
  attempts integer not null default 0,
  error text,
  external_id text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  unique (content_item_id, platform)
);

create index content_publication_jobs_pending_idx
  on public.content_publication_jobs (created_at)
  where status = 'pending';

alter table public.content_publication_jobs enable row level security;
revoke all on public.content_publication_jobs from anon;
grant select on public.content_publication_jobs to authenticated;
grant all on public.content_publication_jobs to service_role;

create policy "publication_jobs_member_select" on public.content_publication_jobs
  for select using (
    exists (
      select 1 from public.content_items ci
      where ci.id = content_item_id
        and internal.account_organization_id(ci.account_id)
          in (select internal.current_user_org_ids())
    )
  );

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
  if not found or config.auto_publish_mode = 'off' then
    return new;
  end if;
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
      insert into public.content_publication_jobs (content_item_id, platform)
      values (new.id, target_platform)
      on conflict (content_item_id, platform) do nothing;
    end if;
  end loop;
  return new;
end;
$$;

revoke all on function public.queue_series_publication() from public;

create trigger queue_series_publication_after_render
  after update of status on public.content_items
  for each row execute function public.queue_series_publication();

create or replace function public.claim_content_publication_job()
returns setof public.content_publication_jobs
language sql
security definer
set search_path = public
as $$
  -- An interrupted upload may have reached YouTube. It must be reviewed,
  -- never retried automatically, to avoid duplicate videos.
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
    order by pending.created_at, pending.id
    for update skip locked
    limit 1
  )
  returning job.*;
$$;

revoke all on function public.claim_content_publication_job() from public;
grant execute on function public.claim_content_publication_job() to service_role;
