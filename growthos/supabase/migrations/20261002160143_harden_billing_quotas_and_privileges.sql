-- Security hardening for billing, quotas and the public Data API.

-- The ledger is an accounting record, not an owner-editable table. Allowing
-- arbitrary INSERTs lets a caller forge reservation rows later consumed by
-- the privileged refund functions.
revoke all on table public.credits_ledger from anon, authenticated;
grant select on table public.credits_ledger to authenticated;
drop policy if exists "credits_ledger_owner_insert" on public.credits_ledger;

-- Trigger functions must never be exposed as RPC endpoints.
revoke all on function public.enforce_account_limit() from public, anon, authenticated;

-- The server, not the caller, determines the monthly AI quota. Keep the old
-- third parameter temporarily for API compatibility, but ignore it.
create or replace function public.consume_ai_quota(
  p_org uuid,
  p_kind text,
  p_limit integer default null
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_plan text;
  v_status text;
  v_override integer;
  v_limit integer;
  v_used integer;
begin
  if p_kind not in ('script', 'quiz', 'quiz_verify') then
    return false;
  end if;

  perform pg_advisory_xact_lock(hashtextextended('ai-quota:' || p_org::text, 0));

  select plan, subscription_status, ai_quota_override
    into v_plan, v_status, v_override
  from public.organizations
  where id = p_org;
  if not found then return false; end if;

  v_limit := coalesce(
    v_override,
    case
      when v_plan = 'business' then 1000
      when v_status not in ('active', 'trialing', 'past_due') or v_status is null then 15
      when v_plan = 'pro' then 240
      else 60
    end
  );

  select count(*) into v_used
  from public.ai_usage
  where organization_id = p_org
    and created_at >= date_trunc('month', now());

  if v_used >= v_limit then return false; end if;
  insert into public.ai_usage (organization_id, kind) values (p_org, p_kind);
  return true;
end;
$$;
revoke all on function public.consume_ai_quota(uuid, text, integer) from public, anon, authenticated;
grant execute on function public.consume_ai_quota(uuid, text, integer) to service_role;

-- Idempotent plan renewal. The Stripe invoice id is persisted in the ledger's
-- unique external_ref so a duplicate event cannot refill spent credits.
create or replace function public.grant_plan_credits(
  p_organization_id uuid,
  p_credits integer,
  p_external_ref text,
  p_reason text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_balance integer;
  v_pack integer;
  v_target integer;
begin
  if p_credits < 0 or p_external_ref is null or p_external_ref = ''
     or p_reason not in ('plan_renewal_starter', 'plan_renewal_pro') then
    return false;
  end if;

  select credits_balance, pack_credits into v_balance, v_pack
  from public.organizations
  where id = p_organization_id
  for update;
  if not found then return false; end if;

  if exists (select 1 from public.credits_ledger where external_ref = p_external_ref) then
    return false;
  end if;

  v_target := p_credits + v_pack;
  update public.organizations
  set credits_balance = v_target
  where id = p_organization_id;

  insert into public.credits_ledger
    (organization_id, delta, reason, balance_after, external_ref)
  values
    (p_organization_id, v_target - v_balance, p_reason, v_target, p_external_ref);
  return true;
end;
$$;
revoke all on function public.grant_plan_credits(uuid, integer, text, text)
  from public, anon, authenticated;
grant execute on function public.grant_plan_credits(uuid, integer, text, text) to service_role;

-- Atomic active-job admission: the advisory lock closes the COUNT/INSERT race.
create or replace function public.create_autoedit_job(
  p_organization_id uuid,
  p_created_by uuid,
  p_profile text,
  p_input_filename text,
  p_input_duration_seconds numeric,
  p_focus text,
  p_player_number text,
  p_style text,
  p_duration_seconds integer
) returns table(id uuid, status text)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('autoedit-active:' || p_organization_id::text, 0));
  if (
    select count(*) from public.autoedit_jobs
    where organization_id = p_organization_id
      and status in ('queued', 'uploading', 'analyzing', 'planning', 'rendering')
  ) >= 3 then
    return;
  end if;

  return query
  insert into public.autoedit_jobs (
    organization_id, created_by, profile, input_filename,
    input_duration_seconds, focus, player_number, style, duration_seconds
  ) values (
    p_organization_id, p_created_by, p_profile, p_input_filename,
    p_input_duration_seconds, p_focus, p_player_number, p_style, p_duration_seconds
  )
  returning autoedit_jobs.id, autoedit_jobs.status;
end;
$$;
revoke all on function public.create_autoedit_job(uuid, uuid, text, text, numeric, text, text, text, integer)
  from public, anon, authenticated;
grant execute on function public.create_autoedit_job(uuid, uuid, text, text, numeric, text, text, text, integer)
  to service_role;
revoke insert on table public.autoedit_jobs from authenticated;

-- Small database-backed limiter suitable for serverless instances.
create table if not exists public.security_rate_limits (
  key text primary key,
  window_started_at timestamptz not null,
  hits integer not null check (hits > 0)
);
alter table public.security_rate_limits enable row level security;
revoke all on table public.security_rate_limits from public, anon, authenticated;

create or replace function public.consume_security_rate_limit(
  p_key text,
  p_limit integer,
  p_window_seconds integer
) returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row public.security_rate_limits%rowtype;
begin
  if p_key is null or length(p_key) > 200
     or p_limit not between 1 and 1000
     or p_window_seconds not between 1 and 86400 then
    return false;
  end if;

  perform pg_advisory_xact_lock(hashtextextended('rate:' || p_key, 0));
  select * into v_row from public.security_rate_limits where key = p_key;
  if not found or v_row.window_started_at <= now() - make_interval(secs => p_window_seconds) then
    insert into public.security_rate_limits (key, window_started_at, hits)
    values (p_key, now(), 1)
    on conflict (key) do update set window_started_at = excluded.window_started_at, hits = 1;
    return true;
  end if;
  if v_row.hits >= p_limit then return false; end if;
  update public.security_rate_limits set hits = hits + 1 where key = p_key;
  return true;
end;
$$;
revoke all on function public.consume_security_rate_limit(text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.consume_security_rate_limit(text, integer, integer) to service_role;

-- Replace permissive default table grants with the exact Data API surface.
revoke all on table
  public.organizations, public.profiles, public.organization_members,
  public.accounts, public.strategies, public.content_items,
  public.content_performance, public.insights, public.recommendations,
  public.niches, public.series, public.content_publication_jobs,
  public.ai_usage
from anon, authenticated;

grant select on table public.organizations to authenticated;
grant update (name) on table public.organizations to authenticated;
grant select, insert, update on table public.profiles to authenticated;
grant select, insert, update, delete on table public.organization_members to authenticated;
grant select, insert, update, delete on table public.accounts to authenticated;
grant select, insert, update on table public.strategies to authenticated;
grant select, insert, update, delete on table public.content_items to authenticated;
grant select, insert on table public.content_performance to authenticated;
grant select, insert, update on table public.insights to authenticated;
grant select, insert, update on table public.recommendations to authenticated;
grant select, insert, update, delete on table public.niches to authenticated;
grant select, insert, update, delete on table public.series to authenticated;
grant select on table public.content_publication_jobs to authenticated;
grant select on table public.ai_usage to authenticated;
