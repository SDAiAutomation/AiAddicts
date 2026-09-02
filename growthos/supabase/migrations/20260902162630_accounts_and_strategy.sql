create table accounts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  platform text not null check (platform in ('tiktok','instagram','youtube')),
  handle text not null,
  niche text,
  status text not null default 'active' check (status in ('active','paused','archived')),
  created_at timestamptz not null default now(),
  unique (organization_id, platform, handle)
);
create index on accounts (organization_id);

-- Resolve an account's organization for RLS on child tables (security definer:
-- callers only need to know the account_id, not have direct SELECT on accounts).
create or replace function public.account_organization_id(acc uuid)
returns uuid
language sql stable security definer set search_path = public as $$
  select organization_id from accounts where id = acc
$$;

create table account_oauth_tokens (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  encrypted_access_token bytea not null,
  encrypted_refresh_token bytea,
  expires_at timestamptz,
  status text not null default 'connected' check (status in ('connected','expired','revoked','error')),
  last_checked_at timestamptz,
  created_at timestamptz not null default now()
);
create index on account_oauth_tokens (account_id);
comment on column account_oauth_tokens.encrypted_access_token is
  'Encrypted application-side (KMS/envelope encryption) before insert. Never store plaintext tokens.';
comment on column account_oauth_tokens.encrypted_refresh_token is
  'Encrypted application-side before insert. Never store plaintext tokens.';

create table strategies (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade unique,
  objectives jsonb not null default '{}',
  audience jsonb not null default '{}',
  tone text,
  priority_formats jsonb not null default '[]',
  brand_constraints text,
  maturity_score integer not null default 0 check (maturity_score between 0 and 100),
  updated_at timestamptz not null default now()
);

alter table accounts enable row level security;
alter table account_oauth_tokens enable row level security;
alter table strategies enable row level security;

create policy "accounts_member_select" on accounts for select
  using (organization_id in (select current_user_org_ids()));
create policy "accounts_write_roles" on accounts for insert
  with check (has_org_role(organization_id, array['owner','strategist']));
create policy "accounts_update_roles" on accounts for update
  using (has_org_role(organization_id, array['owner','strategist']));
create policy "accounts_delete_owner" on accounts for delete
  using (has_org_role(organization_id, array['owner']));

create policy "oauth_tokens_member_select" on account_oauth_tokens for select
  using (account_organization_id(account_id) in (select current_user_org_ids()));
create policy "oauth_tokens_write_roles" on account_oauth_tokens for insert
  with check (has_org_role(account_organization_id(account_id), array['owner','strategist']));
create policy "oauth_tokens_update_roles" on account_oauth_tokens for update
  using (has_org_role(account_organization_id(account_id), array['owner','strategist']));
create policy "oauth_tokens_delete_roles" on account_oauth_tokens for delete
  using (has_org_role(account_organization_id(account_id), array['owner','strategist']));

create policy "strategies_member_select" on strategies for select
  using (account_organization_id(account_id) in (select current_user_org_ids()));
create policy "strategies_write_roles" on strategies for insert
  with check (has_org_role(account_organization_id(account_id), array['owner','strategist']));
create policy "strategies_update_roles" on strategies for update
  using (has_org_role(account_organization_id(account_id), array['owner','strategist']));
