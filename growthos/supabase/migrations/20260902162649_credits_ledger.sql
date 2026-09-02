create table credits_ledger (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  delta integer not null,
  reason text not null,
  related_content_item_id uuid references content_items(id) on delete set null,
  balance_after integer not null,
  created_at timestamptz not null default now()
);
create index on credits_ledger (organization_id);

alter table credits_ledger enable row level security;

create policy "credits_ledger_member_select" on credits_ledger for select
  using (organization_id in (select current_user_org_ids()));
-- Manual adjustments by an owner only; normal consumption is written by the
-- backend using the service role, which bypasses RLS entirely.
create policy "credits_ledger_owner_insert" on credits_ledger for insert
  with check (has_org_role(organization_id, array['owner']));
