create extension if not exists pgcrypto;

create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan text not null default 'starter' check (plan in ('starter','growth','agency','agency_pro')),
  credits_balance integer not null default 0,
  created_at timestamptz not null default now()
);

create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text,
  created_at timestamptz not null default now()
);

create table organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  user_id uuid not null references profiles(id) on delete cascade,
  role text not null check (role in ('owner','strategist','editor','client_viewer')),
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);
create index on organization_members (user_id);
create index on organization_members (organization_id);

-- Helper functions used throughout RLS policies (kept in public, security definer
-- so they can read organization_members regardless of the caller's own RLS view).
create or replace function public.current_user_org_ids()
returns setof uuid
language sql stable security definer set search_path = public as $$
  select organization_id from organization_members where user_id = auth.uid()
$$;

create or replace function public.has_org_role(org uuid, roles text[])
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from organization_members
    where organization_id = org and user_id = auth.uid() and role = any(roles)
  )
$$;

alter table organizations enable row level security;
alter table profiles enable row level security;
alter table organization_members enable row level security;

create policy "profiles_self_select" on profiles for select using (id = auth.uid());
create policy "profiles_self_update" on profiles for update using (id = auth.uid());
create policy "profiles_self_insert" on profiles for insert with check (id = auth.uid());

create policy "organizations_member_select" on organizations for select
  using (id in (select current_user_org_ids()));
create policy "organizations_owner_update" on organizations for update
  using (has_org_role(id, array['owner']));

create policy "members_select_same_org" on organization_members for select
  using (organization_id in (select current_user_org_ids()));
create policy "members_owner_insert" on organization_members for insert
  with check (has_org_role(organization_id, array['owner']));
create policy "members_owner_update" on organization_members for update
  using (has_org_role(organization_id, array['owner']));
create policy "members_owner_delete" on organization_members for delete
  using (has_org_role(organization_id, array['owner']));
