-- The `authenticated` warning is expected in principle (RLS policies run as
-- the querying role, so authenticated needs EXECUTE) but PostgREST also
-- exposes every function in an exposed schema as a callable RPC endpoint --
-- these were never meant to be a public API. Move them out of `public`
-- entirely into a schema PostgREST doesn't expose, closing that surface
-- while RLS policies keep working (Postgres resolves schema-qualified calls
-- regardless of exposure config).

create schema if not exists internal;

create or replace function internal.current_user_org_ids()
returns setof uuid
language sql stable security definer set search_path = pg_catalog as $$
  select organization_id from public.organization_members where user_id = auth.uid()
$$;

create or replace function internal.has_org_role(org uuid, roles text[])
returns boolean
language sql stable security definer set search_path = pg_catalog as $$
  select exists (
    select 1 from public.organization_members
    where organization_id = org and user_id = auth.uid() and role = any(roles)
  )
$$;

create or replace function internal.account_organization_id(acc uuid)
returns uuid
language sql stable security definer set search_path = pg_catalog as $$
  select organization_id from public.accounts where id = acc
$$;

create or replace function internal.content_item_organization_id(item uuid)
returns uuid
language sql stable security definer set search_path = pg_catalog as $$
  select a.organization_id from public.content_items c
  join public.accounts a on a.id = c.account_id
  where c.id = item
$$;

revoke execute on function internal.current_user_org_ids() from public, anon;
revoke execute on function internal.has_org_role(uuid, text[]) from public, anon;
revoke execute on function internal.account_organization_id(uuid) from public, anon;
revoke execute on function internal.content_item_organization_id(uuid) from public, anon;
grant usage on schema internal to authenticated;
grant execute on function internal.current_user_org_ids() to authenticated;
grant execute on function internal.has_org_role(uuid, text[]) to authenticated;
grant execute on function internal.account_organization_id(uuid) to authenticated;
grant execute on function internal.content_item_organization_id(uuid) to authenticated;

-- Repoint every policy at the internal.* functions.
alter policy "organizations_member_select" on organizations
  using (id in (select internal.current_user_org_ids()));
alter policy "organizations_owner_update" on organizations
  using (internal.has_org_role(id, array['owner']));

alter policy "members_select_same_org" on organization_members
  using (organization_id in (select internal.current_user_org_ids()));
alter policy "members_owner_insert" on organization_members
  with check (internal.has_org_role(organization_id, array['owner']));
alter policy "members_owner_update" on organization_members
  using (internal.has_org_role(organization_id, array['owner']));
alter policy "members_owner_delete" on organization_members
  using (internal.has_org_role(organization_id, array['owner']));

alter policy "accounts_member_select" on accounts
  using (organization_id in (select internal.current_user_org_ids()));
alter policy "accounts_write_roles" on accounts
  with check (internal.has_org_role(organization_id, array['owner','strategist']));
alter policy "accounts_update_roles" on accounts
  using (internal.has_org_role(organization_id, array['owner','strategist']));
alter policy "accounts_delete_owner" on accounts
  using (internal.has_org_role(organization_id, array['owner']));

alter policy "oauth_tokens_member_select" on account_oauth_tokens
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
alter policy "oauth_tokens_write_roles" on account_oauth_tokens
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
alter policy "oauth_tokens_update_roles" on account_oauth_tokens
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
alter policy "oauth_tokens_delete_roles" on account_oauth_tokens
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));

alter policy "strategies_member_select" on strategies
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
alter policy "strategies_write_roles" on strategies
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
alter policy "strategies_update_roles" on strategies
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));

alter policy "content_items_member_select" on content_items
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
alter policy "content_items_write_roles" on content_items
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist','editor']));
alter policy "content_items_update_roles" on content_items
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist','editor']));
alter policy "content_items_delete_roles" on content_items
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));

alter policy "content_performance_member_select" on content_performance
  using (internal.content_item_organization_id(content_item_id) in (select internal.current_user_org_ids()));
alter policy "content_performance_write_roles" on content_performance
  with check (internal.has_org_role(internal.content_item_organization_id(content_item_id), array['owner','strategist','editor']));

alter policy "insights_member_select" on insights
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
alter policy "insights_write_roles" on insights
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
alter policy "insights_update_roles" on insights
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));

alter policy "recommendations_member_select" on recommendations
  using (internal.account_organization_id(account_id) in (select internal.current_user_org_ids()));
alter policy "recommendations_write_roles" on recommendations
  with check (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist']));
alter policy "recommendations_update_roles" on recommendations
  using (internal.has_org_role(internal.account_organization_id(account_id), array['owner','strategist','editor']));

alter policy "credits_ledger_member_select" on credits_ledger
  using (organization_id in (select internal.current_user_org_ids()));
alter policy "credits_ledger_owner_insert" on credits_ledger
  with check (internal.has_org_role(organization_id, array['owner']));

alter policy "audit_select_own_org" on audit.events
  using (tenant_id in (select internal.current_user_org_ids()));

-- Now unreferenced: drop the old public copies entirely.
drop function public.current_user_org_ids();
drop function public.has_org_role(uuid, text[]);
drop function public.account_organization_id(uuid);
drop function public.content_item_organization_id(uuid);
