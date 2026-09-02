create schema if not exists audit;

create table audit.events (
  id uuid primary key default gen_random_uuid(),
  occurred_at timestamptz not null default now(),
  actor_id uuid,
  tenant_id uuid,
  action text not null,
  resource_type text,
  resource_id uuid,
  request_id uuid,
  result text not null check (result in ('success','failure')),
  risk_level text not null default 'low' check (risk_level in ('low','medium','high')),
  metadata jsonb not null default '{}'
);
create index on audit.events (tenant_id);
create index on audit.events (occurred_at);
create index on audit.events (actor_id);

comment on table audit.events is
  'Append-only security audit trail. Never log password, access_token, refresh_token or api_key values in metadata. Written by the backend service role only (bypasses RLS/grants) -- authenticated/anon are never granted INSERT here.';

-- Belt and suspenders: even the table owner/service_role going through normal
-- SQL (not a superuser bypass) gets blocked from mutating history.
create or replace function audit.forbid_mutation()
returns trigger
language plpgsql as $$
begin
  raise exception 'audit.events is append-only: % is not allowed', TG_OP;
end;
$$;

create trigger audit_events_no_update
  before update on audit.events
  for each row execute function audit.forbid_mutation();

create trigger audit_events_no_delete
  before delete on audit.events
  for each row execute function audit.forbid_mutation();

alter table audit.events enable row level security;

-- Members can read their own tenant's audit trail. No insert/update/delete
-- policy is defined for authenticated/anon on purpose: writes only happen
-- through the backend's service_role connection, which bypasses RLS.
create policy "audit_select_own_org" on audit.events for select
  using (tenant_id in (select current_user_org_ids()));

grant usage on schema audit to authenticated;
grant select on audit.events to authenticated;
revoke insert, update, delete on audit.events from authenticated, anon;
