do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema auth; create schema internal;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('test.uid', true), '')::uuid $$;
create table public.organizations(id uuid primary key);
create table public.organization_members(organization_id uuid, user_id uuid, role text);
create function internal.has_org_role(org uuid, roles text[]) returns boolean language sql stable security definer as $$
  select exists(select 1 from public.organization_members where organization_id=org and user_id=auth.uid() and role=any(roles)) $$;
create function internal.current_user_org_ids() returns setof uuid language sql stable security definer as $$ select organization_id from public.organization_members where user_id=auth.uid() $$;
grant usage on schema public, internal, auth to anon, authenticated, service_role;
grant execute on all functions in schema internal, auth to anon, authenticated, service_role;
