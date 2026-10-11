-- REVIEW ONLY. Do not apply to production without explicit approval.
-- Atomically update only the creative_quality key of score_details, with
-- a row lock and generation/version guards. Requires trusted service-role caller.
create or replace function public.store_creative_quality_report(
  p_content_item_id uuid,
  p_script_version integer,
  p_video_script_version integer,
  p_current_version_id uuid,
  p_report jsonb
)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_item public.content_items%rowtype;
begin
  if p_current_version_id is null or p_video_script_version is null
     or p_script_version is null
     or p_report is null or jsonb_typeof(p_report) <> 'object'
     or p_report->>'schema_version' is distinct from 'creative_quality:v1'
     or p_report->'enforcement_enabled' is distinct from 'false'::jsonb
     or p_report->'automatic_edits_applied' is distinct from 'false'::jsonb
     or coalesce(p_report->>'decision', '') not in ('pass','review','block')
     or jsonb_typeof(p_report->'issues') is distinct from 'array'
     or case when jsonb_typeof(p_report->'issues') = 'array'
             then jsonb_array_length(p_report->'issues') > 50
             else true end
     or octet_length(p_report::text) > 40000
     or coalesce(p_report->>'stage','') not in ('script','render','combined')
     or p_report->>'script_version' is distinct from p_script_version::text
     or p_report->>'video_script_version' is distinct from p_video_script_version::text
     or p_report->>'current_version_id' is distinct from p_current_version_id::text
  then
    raise exception 'Invalid creative quality report';
  end if;

  select * into v_item
  from public.content_items
  where id = p_content_item_id
  for update;
  if not found then return false; end if;
  if v_item.script_version is distinct from p_script_version
     or (p_video_script_version is not null and
         v_item.video_script_version is distinct from p_video_script_version)
     or v_item.current_version_id is distinct from p_current_version_id
  then return false; end if;

  update public.content_items
  set score_details = coalesce(v_item.score_details, '{}'::jsonb)
                      || jsonb_build_object('creative_quality', p_report)
  where id = p_content_item_id;
  return true;
end;
$$;

-- Permission must be restricted to service_role: this function is not
-- callable by user sessions, even if a user knows another content item UUID.
revoke all on function public.store_creative_quality_report(uuid,integer,integer,uuid,jsonb) from public;
revoke all on function public.store_creative_quality_report(uuid,integer,integer,uuid,jsonb) from anon;
revoke all on function public.store_creative_quality_report(uuid,integer,integer,uuid,jsonb) from authenticated;
grant execute on function public.store_creative_quality_report(uuid,integer,integer,uuid,jsonb) to service_role;
