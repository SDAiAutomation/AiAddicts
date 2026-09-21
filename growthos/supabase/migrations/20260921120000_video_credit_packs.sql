-- Packs de vidéos supplémentaires (achat unique, ex. 30 vidéos ≈ une série
-- quotidienne). Le solde mensuel est remis à zéro à chaque facture payée
-- (voir webhook Stripe `grantPlanCredits`) : les crédits achetés ne doivent PAS
-- être écrasés. Modèle :
--   credits_balance = crédits mensuels restants + pack_credits
--   pack_credits    = part du solde qui vient de packs (n'expire pas)
-- La consommation utilise d'abord les crédits mensuels, puis le pack.
-- `credits_ledger.reason` mémorise la source du débit ('..._pack') pour que le
-- remboursement recrédite la bonne réserve.
--
-- `authenticated` n'a le droit de modifier que organizations.name (migration
-- stripe_billing) : pack_credits n'est écrit que par service_role / RPC.

alter table organizations
  add column if not exists pack_credits integer not null default 0 check (pack_credits >= 0);

-- Référence externe (id de Checkout Session) : Stripe peut rejouer un webhook,
-- un même achat ne doit créditer qu'une fois.
alter table credits_ledger add column if not exists external_ref text;
create unique index if not exists credits_ledger_external_ref_key
  on credits_ledger (external_ref) where external_ref is not null;

create or replace function public.grant_pack_credits(
  p_organization_id uuid, p_credits integer, p_external_ref text
) returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_balance integer;
begin
  if p_credits is null or p_credits <= 0 or p_external_ref is null then
    return false;
  end if;

  select credits_balance into v_balance
  from organizations where id = p_organization_id for update;
  if v_balance is null then return false; end if;

  -- Déjà crédité pour cette session : rien à faire (idempotent).
  if exists (select 1 from credits_ledger where external_ref = p_external_ref) then
    return false;
  end if;

  update organizations
  set credits_balance = credits_balance + p_credits,
      pack_credits = pack_credits + p_credits
  where id = p_organization_id;

  insert into credits_ledger
    (organization_id, delta, reason, balance_after, external_ref)
  values
    (p_organization_id, p_credits, 'pack_purchase', v_balance + p_credits, p_external_ref);
  return true;
end;
$$;

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
  v_pack integer;
  v_net_reservation integer;
  v_from_pack boolean;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then return false; end if;

  select plan, credits_balance, pack_credits into v_plan, v_balance, v_pack
  from organizations where id = v_org_id for update;

  if v_plan = 'business' then return true; end if;

  select coalesce(sum(delta), 0) into v_net_reservation
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in (
      'video_generation_reserved', 'video_generation_refund',
      'video_generation_reserved_pack', 'video_generation_refund_pack'
    );

  if v_net_reservation < 0 then return true; end if;
  if v_balance <= 0 then return false; end if;

  -- Crédits mensuels restants = solde - pack ; on les consomme en premier.
  v_from_pack := (v_balance - v_pack) <= 0;

  update organizations
  set credits_balance = credits_balance - 1,
      pack_credits = case when v_from_pack then pack_credits - 1 else pack_credits end
  where id = v_org_id;
  insert into credits_ledger
    (organization_id, delta, reason, related_content_item_id, balance_after)
  values
    (v_org_id, -1,
     case when v_from_pack then 'video_generation_reserved_pack' else 'video_generation_reserved' end,
     p_content_item_id, v_balance - 1);
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
  v_net_reservation integer;
  v_pack_net integer;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then return false; end if;

  select plan, credits_balance into v_plan, v_balance
  from organizations where id = v_org_id for update;

  if v_plan = 'business' then return false; end if;

  select coalesce(sum(delta), 0) into v_net_reservation
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in (
      'video_generation_reserved', 'video_generation_refund',
      'video_generation_reserved_pack', 'video_generation_refund_pack'
    );

  if v_net_reservation >= 0 then return false; end if;

  -- Le débit à rembourser venait-il du pack ? (net < 0 sur les lignes _pack)
  select coalesce(sum(delta), 0) into v_pack_net
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in ('video_generation_reserved_pack', 'video_generation_refund_pack');

  if v_pack_net < 0 then
    update organizations
    set credits_balance = credits_balance + 1, pack_credits = pack_credits + 1
    where id = v_org_id;
    insert into credits_ledger
      (organization_id, delta, reason, related_content_item_id, balance_after)
    values
      (v_org_id, 1, 'video_generation_refund_pack', p_content_item_id, v_balance + 1);
  else
    update organizations set credits_balance = credits_balance + 1 where id = v_org_id;
    insert into credits_ledger
      (organization_id, delta, reason, related_content_item_id, balance_after)
    values
      (v_org_id, 1, 'video_generation_refund', p_content_item_id, v_balance + 1);
  end if;
  return true;
end;
$$;

revoke all on function public.grant_pack_credits(uuid, integer, text) from public, anon, authenticated;
grant execute on function public.grant_pack_credits(uuid, integer, text) to service_role;
revoke all on function public.reserve_generation_credit(uuid) from public, anon, authenticated;
revoke all on function public.refund_generation_credit(uuid) from public, anon, authenticated;
grant execute on function public.reserve_generation_credit(uuid) to service_role;
grant execute on function public.refund_generation_credit(uuid) to service_role;
