-- Plan Business sur devis : jusqu'ici `plan = 'business'` contournait TOUT
-- décompte de crédits (coût sans plafond). Un quota mensuel par organisation
-- permet de vendre un volume engagé :
--   - monthly_credit_quota NULL  => comportement historique (illimité, opérateur) ;
--   - monthly_credit_quota = N   => crédits décomptés normalement, solde remis à N
--     chaque mois (non cumulatif, comme la recharge Stripe des plans Starter/Pro).
-- La recharge est paresseuse : elle se fait à la première réservation après
-- l'échéance, sans tâche planifiée à surveiller.

alter table public.organizations
  add column monthly_credit_quota integer
    check (monthly_credit_quota is null or monthly_credit_quota >= 0),
  add column credits_refilled_at timestamptz;

comment on column public.organizations.monthly_credit_quota is
  'Business uniquement : crédits vidéo remis chaque mois. NULL = illimité (historique).';
comment on column public.organizations.credits_refilled_at is
  'Ancre de la dernière recharge mensuelle du quota Business (avance par pas d''un mois).';

create or replace function public.refill_business_credits_if_due(p_org_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_quota integer;
  v_refilled timestamptz;
  v_balance integer;
  v_months integer;
  v_anchor timestamptz;
begin
  select monthly_credit_quota, credits_refilled_at, credits_balance
    into v_quota, v_refilled, v_balance
  from organizations
  where id = p_org_id and plan = 'business'
  for update;

  if not found or v_quota is null then return; end if;

  if v_refilled is null then
    v_anchor := now();  -- première activation du quota
  else
    v_months := extract(year from age(now(), v_refilled))::int * 12
              + extract(month from age(now(), v_refilled))::int;
    if v_months < 1 then return; end if;
    v_anchor := v_refilled + (v_months * interval '1 month');
  end if;

  update organizations
  set credits_balance = v_quota, credits_refilled_at = v_anchor
  where id = p_org_id;
  insert into credits_ledger (organization_id, delta, reason, balance_after)
  values (p_org_id, v_quota - v_balance, 'monthly_refill', v_quota);
end;
$$;

revoke all on function public.refill_business_credits_if_due(uuid) from public, anon, authenticated;
grant execute on function public.refill_business_credits_if_due(uuid) to service_role;

create or replace function public.reserve_generation_credit(p_content_item_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_org_id uuid;
  v_plan text;
  v_balance integer;
  v_quota integer;
  v_net_reservation integer;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then return false; end if;

  select plan, credits_balance, monthly_credit_quota into v_plan, v_balance, v_quota
  from organizations where id = v_org_id for update;

  if v_plan = 'business' then
    if v_quota is null then return true; end if;  -- illimité (historique)
    perform refill_business_credits_if_due(v_org_id);
    select credits_balance into v_balance from organizations where id = v_org_id;
  end if;

  select coalesce(sum(delta), 0) into v_net_reservation
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in ('video_generation_reserved', 'video_generation_refund');

  if v_net_reservation < 0 then return true; end if;
  if v_balance <= 0 then return false; end if;

  update organizations set credits_balance = credits_balance - 1
  where id = v_org_id;
  insert into credits_ledger
    (organization_id, delta, reason, related_content_item_id, balance_after)
  values
    (v_org_id, -1, 'video_generation_reserved', p_content_item_id, v_balance - 1);
  return true;
end;
$$;

create or replace function public.refund_generation_credit(p_content_item_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_org_id uuid;
  v_plan text;
  v_balance integer;
  v_quota integer;
  v_net_reservation integer;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then return false; end if;

  select plan, credits_balance, monthly_credit_quota into v_plan, v_balance, v_quota
  from organizations where id = v_org_id for update;

  if v_plan = 'business' and v_quota is null then return false; end if;

  select coalesce(sum(delta), 0) into v_net_reservation
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in ('video_generation_reserved', 'video_generation_refund');

  if v_net_reservation >= 0 then return false; end if;

  update organizations set credits_balance = credits_balance + 1
  where id = v_org_id;
  insert into credits_ledger
    (organization_id, delta, reason, related_content_item_id, balance_after)
  values
    (v_org_id, 1, 'video_generation_refund', p_content_item_id, v_balance + 1);
  return true;
end;
$$;

revoke all on function public.reserve_generation_credit(uuid) from public, anon, authenticated;
revoke all on function public.refund_generation_credit(uuid) from public, anon, authenticated;
grant execute on function public.reserve_generation_credit(uuid) to service_role;
grant execute on function public.refund_generation_credit(uuid) to service_role;
