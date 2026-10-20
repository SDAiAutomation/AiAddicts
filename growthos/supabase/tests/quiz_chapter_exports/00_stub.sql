do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
end $$;
create schema auth; create schema internal;
create function auth.role() returns text language sql stable as $$ select current_setting('test.role', true) $$;
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('test.uid', true), '')::uuid $$;
create table public.organization_members(organization_id uuid, user_id uuid, role text);
create table public.accounts(id uuid primary key, organization_id uuid);
create table public.content_versions(id uuid primary key default gen_random_uuid());
create table public.content_items(id uuid primary key default gen_random_uuid(), account_id uuid, status text, video_url text, script jsonb, current_version_id uuid);
create table public.series(id uuid primary key default gen_random_uuid(), content_format text, quiz_config jsonb);
create function internal.has_org_role(org uuid, roles text[]) returns boolean language sql stable security definer as $$
  select exists(select 1 from public.organization_members where organization_id=org and user_id=auth.uid() and role=any(roles)) $$;
create function internal.account_organization_id(acc uuid) returns uuid language sql stable security definer as $$ select organization_id from public.accounts where id=acc $$;
create function internal.current_user_org_ids() returns setof uuid language sql stable security definer as $$ select organization_id from public.organization_members where user_id=auth.uid() $$;
grant usage on schema public, internal, auth to anon, authenticated, service_role;
grant select on all tables in schema public to authenticated;
grant all on all tables in schema public to service_role;
grant execute on all functions in schema internal, auth to anon, authenticated, service_role;
