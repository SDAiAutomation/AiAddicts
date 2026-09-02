create table content_items (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  title text not null,
  status text not null default 'idea' check (status in ('idea','script','video','quality_check','published','failed')),
  script jsonb,
  quality_score integer check (quality_score between 0 and 100),
  video_url text,
  published_at timestamptz,
  created_at timestamptz not null default now()
);
create index on content_items (account_id);
create index on content_items (status);

create or replace function public.content_item_organization_id(item uuid)
returns uuid
language sql stable security definer set search_path = public as $$
  select a.organization_id from content_items c join accounts a on a.id = c.account_id where c.id = item
$$;

create table content_performance (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references content_items(id) on delete cascade,
  captured_at timestamptz not null default now(),
  views integer,
  watch_time_pct numeric(5,2),
  likes integer,
  comments integer,
  shares integer,
  followers_delta integer,
  leads integer
);
create index on content_performance (content_item_id);

create table insights (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  kind text not null check (kind in ('hook','format','topic','schedule')),
  label text not null,
  performance_score numeric(5,2),
  sample_size integer not null default 0,
  updated_at timestamptz not null default now()
);
create index on insights (account_id);

create table recommendations (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id) on delete cascade,
  generated_at timestamptz not null default now(),
  body text not null,
  reasoning text,
  confidence text not null check (confidence in ('high','medium','low')),
  status text not null default 'pending' check (status in ('pending','applied','ignored')),
  resolved_at timestamptz
);
create index on recommendations (account_id);

alter table content_items enable row level security;
alter table content_performance enable row level security;
alter table insights enable row level security;
alter table recommendations enable row level security;

create policy "content_items_member_select" on content_items for select
  using (account_organization_id(account_id) in (select current_user_org_ids()));
create policy "content_items_write_roles" on content_items for insert
  with check (has_org_role(account_organization_id(account_id), array['owner','strategist','editor']));
create policy "content_items_update_roles" on content_items for update
  using (has_org_role(account_organization_id(account_id), array['owner','strategist','editor']));
create policy "content_items_delete_roles" on content_items for delete
  using (has_org_role(account_organization_id(account_id), array['owner','strategist']));

create policy "content_performance_member_select" on content_performance for select
  using (content_item_organization_id(content_item_id) in (select current_user_org_ids()));
create policy "content_performance_write_roles" on content_performance for insert
  with check (has_org_role(content_item_organization_id(content_item_id), array['owner','strategist','editor']));

create policy "insights_member_select" on insights for select
  using (account_organization_id(account_id) in (select current_user_org_ids()));
create policy "insights_write_roles" on insights for insert
  with check (has_org_role(account_organization_id(account_id), array['owner','strategist']));
create policy "insights_update_roles" on insights for update
  using (has_org_role(account_organization_id(account_id), array['owner','strategist']));

create policy "recommendations_member_select" on recommendations for select
  using (account_organization_id(account_id) in (select current_user_org_ids()));
create policy "recommendations_write_roles" on recommendations for insert
  with check (has_org_role(account_organization_id(account_id), array['owner','strategist']));
create policy "recommendations_update_roles" on recommendations for update
  using (has_org_role(account_organization_id(account_id), array['owner','strategist','editor']));
