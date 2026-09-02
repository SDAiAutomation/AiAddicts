-- Supabase grants EXECUTE directly to anon/authenticated/service_role via
-- default privileges at creation time, separate from the PUBLIC pseudo-role,
-- so `revoke ... from public` alone did not remove anon's direct grant.
-- Revoke explicitly per role, then re-grant only what's needed.
revoke execute on function public.current_user_org_ids() from anon, authenticated;
revoke execute on function public.has_org_role(uuid, text[]) from anon, authenticated;
revoke execute on function public.account_organization_id(uuid) from anon, authenticated;
revoke execute on function public.content_item_organization_id(uuid) from anon, authenticated;

grant execute on function public.current_user_org_ids() to authenticated;
grant execute on function public.has_org_role(uuid, text[]) to authenticated;
grant execute on function public.account_organization_id(uuid) to authenticated;
grant execute on function public.content_item_organization_id(uuid) to authenticated;
