-- The final render update can change the script. The recommendation trigger
-- increments script_version after the render trigger has copied its old value
-- to video_script_version; keep both versions aligned for that rendered script.
create or replace function public.invalidate_recommendation_on_script_change()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if old.script is distinct from new.script then
    new.updated_at := clock_timestamp();
    new.recommendation_report := null;
    new.story_features := null;
    if new.script_version = old.script_version then
      new.script_version := old.script_version + 1;
    end if;
    if old.status = 'generating'
       and new.status in ('video', 'quality_check')
       and new.video_url ~ '^https?://' then
      new.video_script_version := new.script_version;
    end if;
  end if;
  return new;
end;
$$;

-- Repair only rows whose current script and video exactly match the saved
-- immutable render. A genuine post-render edit remains marked as stale.
update public.content_items ci
set video_script_version = ci.script_version
from public.content_versions cv
where ci.current_version_id = cv.id
  and cv.content_item_id = ci.id
  and ci.status in ('video', 'quality_check', 'published')
  and ci.video_script_version is not null
  and ci.video_script_version is distinct from ci.script_version
  and ci.script is not distinct from cv.script
  and ci.video_url = cv.video_url;
