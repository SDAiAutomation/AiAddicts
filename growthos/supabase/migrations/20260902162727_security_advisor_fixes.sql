-- Fix 1: mutable search_path on the audit trigger function (function_search_path_mutable).
create or replace function audit.forbid_mutation()
returns trigger
language plpgsql
set search_path = audit, pg_temp
as $$
begin
  raise exception 'audit.events is append-only: % is not allowed', TG_OP;
end;
$$;

-- Fix 2: the RLS helper functions are SECURITY DEFINER and were left publicly
-- executable, so PostgREST exposes them at /rest/v1/rpc/* to anon too.
-- `authenticated` still needs EXECUTE (RLS policies run as the querying role),
-- but `anon` (never logged in, nothing to scope) should not be able to call
-- them directly at all.
revoke execute on function public.current_user_org_ids() from public;
revoke execute on function public.has_org_role(uuid, text[]) from public;
revoke execute on function public.account_organization_id(uuid) from public;
revoke execute on function public.content_item_organization_id(uuid) from public;

grant execute on function public.current_user_org_ids() to authenticated;
grant execute on function public.has_org_role(uuid, text[]) to authenticated;
grant execute on function public.account_organization_id(uuid) to authenticated;
grant execute on function public.content_item_organization_id(uuid) to authenticated;
