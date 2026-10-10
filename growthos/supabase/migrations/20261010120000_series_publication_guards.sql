-- Keep the stored script of a published series episode identical to the
-- published artifact, even when an update bypasses the web application.
create or replace function public.invalidate_series_episode_on_script_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  -- The renderer persists its finalized script and video in one update.
  -- This is a completed render, not an editorial edit to invalidate.
  if old.status = 'generating'
     and new.status in ('video', 'quality_check')
     and new.video_url ~ '^https?://' then
    return new;
  end if;

  if old.series_id is null or old.script is not distinct from new.script then
    return new;
  end if;

  if old.status = 'published' then
    raise exception 'A published series episode script cannot be changed'
      using errcode = '23514';
  end if;

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
  return new;
end;
$$;

-- A restore changes the script as well as the selected video. Refuse it for
-- published series episodes before the trigger raises an exception.
create or replace function public.restore_content_version(p_content_item_id uuid, p_version_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_account uuid;
  v_ver public.content_versions%rowtype;
begin
  select account_id into v_account from public.content_items
  where id = p_content_item_id;
  if v_account is null then return false; end if;

  if auth.role() <> 'service_role'
     and not internal.has_org_role(internal.account_organization_id(v_account),
                                   array['owner','strategist','editor']) then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  select * into v_ver from public.content_versions
  where id = p_version_id and content_item_id = p_content_item_id;
  if not found then return false; end if;

  update public.content_items set
    video_url = v_ver.video_url,
    poster_url = coalesce(v_ver.poster_url, poster_url),
    script = coalesce(v_ver.script, script),
    current_version_id = v_ver.id,
    original_video_url = null,
    trim_start = 0,
    trim_end = null,
    trim_status = null,
    updated_at = now()
  where id = p_content_item_id
    and (status in ('video', 'quality_check')
         or (status = 'published' and series_id is null))
    and coalesce(trim_status, '') not in ('pending', 'processing');
  return found;
end;
$$;

-- A quality_check row explicitly needs review. A rendered video must belong
-- to the current script version; stale artifacts must never be published.
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
     or new.status <> 'video'
     or old.status = new.status
     or old.status = 'published'
     or new.video_script_version is distinct from new.script_version
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
     and (new.quality_score is null or new.quality_score < 70
          or new.quality_flags <> '[]'::jsonb) then
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
              when public.content_publication_jobs.status = 'needs_review' then 'needs_review'
              else 'pending'
            end,
            error = case
              when public.content_publication_jobs.status = 'needs_review'
                then public.content_publication_jobs.error
              else null
            end;
    end if;
  end loop;
  return new;
end;
$$;
