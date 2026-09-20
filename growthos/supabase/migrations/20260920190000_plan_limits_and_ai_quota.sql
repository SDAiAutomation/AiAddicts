-- Garde-fous de rentabilité : limite de comptes par plan + quota mensuel
-- d'appels d'assistance IA (script, questions de quiz, contre-vérification).
--
-- Les valeurs par plan vivent dans growthos-web `lib/stripe-plans.ts`
-- (PLAN_ACCOUNT_LIMITS, PLAN_AI_QUOTA) : en cas de changement, garder le
-- trigger ci-dessous aligné avec PLAN_ACCOUNT_LIMITS.
--
-- Deux colonnes de dérogation par organisation (ex. l'espace de dogfooding),
-- NON modifiables par l'utilisateur : `authenticated` n'a le droit d'UPDATE que
-- sur `organizations.name` (voir stripe_billing.sql).

alter table public.organizations
  add column if not exists account_limit_override integer,
  add column if not exists ai_quota_override integer;

comment on column public.organizations.account_limit_override is
  'Remplace la limite de comptes du plan (null = limite du plan).';
comment on column public.organizations.ai_quota_override is
  'Remplace le quota mensuel d''appels IA du plan (null = quota du plan).';

-- Limite de comptes : filet de sécurité côté base (un membre peut insérer dans
-- `accounts` directement via l'API REST). Ignoré pour le backend (service_role,
-- pas d'utilisateur authentifié) : le pipeline Python crée ses comptes lui-même.
create or replace function public.enforce_account_limit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  org_plan text;
  org_override integer;
  lim integer;
  n integer;
begin
  if auth.uid() is null then
    return new;
  end if;

  select plan, account_limit_override into org_plan, org_override
  from public.organizations where id = new.organization_id;

  lim := coalesce(
    org_override,
    case org_plan when 'starter' then 1 when 'pro' then 5 else null end
  );
  if lim is null then
    return new;
  end if;

  select count(*) into n from public.accounts where organization_id = new.organization_id;
  if n >= lim then
    raise exception 'ACCOUNT_LIMIT_REACHED';
  end if;
  return new;
end;
$$;

drop trigger if exists accounts_enforce_limit on public.accounts;
create trigger accounts_enforce_limit
  before insert on public.accounts
  for each row execute function public.enforce_account_limit();

-- Quota d'assistance IA : une ligne par appel, décompte mensuel.
create table if not exists public.ai_usage (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  kind text not null,
  created_at timestamptz not null default now()
);
create index if not exists ai_usage_org_created_idx on public.ai_usage (organization_id, created_at);

alter table public.ai_usage enable row level security;
create policy "ai_usage_member_select" on public.ai_usage for select
  using (organization_id in (select internal.current_user_org_ids()));
-- Aucune policy d'écriture : les lignes ne s'ajoutent que via consume_ai_quota().

-- Consomme 1 appel si le quota mensuel n'est pas atteint (atomique par
-- organisation). `p_limit` null = illimité. Renvoie false si refusé.
create or replace function public.consume_ai_quota(p_org uuid, p_kind text, p_limit integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  used integer;
begin
  if p_org not in (select internal.current_user_org_ids()) then
    return false;
  end if;

  perform pg_advisory_xact_lock(hashtext(p_org::text));

  select count(*) into used
  from public.ai_usage
  where organization_id = p_org and created_at >= date_trunc('month', now());

  if p_limit is not null and used >= p_limit then
    return false;
  end if;

  insert into public.ai_usage (organization_id, kind) values (p_org, p_kind);
  return true;
end;
$$;

revoke all on function public.consume_ai_quota(uuid, text, integer) from public, anon;
grant execute on function public.consume_ai_quota(uuid, text, integer) to authenticated;
