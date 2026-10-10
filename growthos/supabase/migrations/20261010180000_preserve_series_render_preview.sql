-- The renderer saves its finalized script and video in one update. Do not
-- invalidate that completed render as though it were a manual script edit.
create or replace function public.invalidate_series_episode_on_script_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
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
