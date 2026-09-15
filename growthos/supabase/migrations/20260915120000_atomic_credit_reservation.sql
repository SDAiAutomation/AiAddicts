-- Réserve le crédit avant les appels ElevenLabs/OpenAI. L'ancien flux
-- vérifiait le solde avant la génération puis débitait après : deux workers
-- pouvaient donc consommer des APIs payantes avec un seul crédit restant.

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
  v_net_reservation integer;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then return false; end if;

  select plan, credits_balance into v_plan, v_balance
  from organizations where id = v_org_id for update;

  if v_plan = 'business' then return true; end if;

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
  v_net_reservation integer;
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

-- L'ancienne RPC reste disponible pendant le déploiement afin qu'un worker
-- d'une version précédente déjà lancé ne casse pas en plein traitement. Elle
-- pourra être supprimée dans une migration ultérieure.
