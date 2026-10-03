-- Lot L0 (audit bible 2026-10-03) : politique de crédits à la régénération.
--
-- Avant : une fois la réservation d'un content_item nette à -1, toute
-- régénération complète (édition du script puis nouvelle mise en file) passait
-- sans débit. Illimité pour 1 crédit, alors qu'une régénération coûte ~0,34 $.
--
-- Politique décidée : UNE retouche gratuite par vidéo, les suivantes coûtent
-- 1 crédit. Un « run » = une génération terminée avec succès.
--
--   completed_generations = nombre de runs terminés pour l'élément
--   crédits dus (held) pour lancer le run suivant = greatest(1, completed)
--     run 1 (completed=0) -> 1 crédit    run 2 (completed=1) -> 0 (retouche)
--     run 3 (completed=2) -> +1          run 4 (completed=3) -> +1 ...
--   crédits justifiés après un échec = 0 si rien n'a jamais abouti, sinon
--     greatest(1, completed - 1) ; l'excédent est remboursé.
--
-- Idempotence : reprise après crash, double clic ou requête rejouée retrouvent
-- les crédits déjà détenus (held >= dus) et ne débitent pas deux fois.
-- Le plan business reste illimité.

alter table public.content_items
  add column if not exists completed_generations integer not null default 0
  check (completed_generations >= 0);

-- Éléments déjà rendus avant cette migration : leur prochain run est la
-- retouche gratuite.
update public.content_items
set completed_generations = 1
where completed_generations = 0 and video_url is not null;

-- Numéro de run rattaché à chaque écriture de débit/remboursement (traçabilité).
alter table public.credits_ledger
  add column if not exists generation_run integer;

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
  v_completed integer;
  v_held integer;
  v_required integer;
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

  -- Lu après le verrou de l'organisation : deux réservations concurrentes se
  -- sérialisent et voient le même état.
  select completed_generations into v_completed
  from content_items where id = p_content_item_id;

  select coalesce(-sum(delta), 0) into v_held
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in (
      'video_generation_reserved', 'video_generation_refund',
      'video_generation_reserved_pack', 'video_generation_refund_pack'
    );

  v_required := greatest(1, v_completed);
  if v_held >= v_required then return true; end if;
  if v_balance <= 0 then return false; end if;

  -- Crédits mensuels restants = solde - pack ; on les consomme en premier.
  v_from_pack := (v_balance - v_pack) <= 0;

  update organizations
  set credits_balance = credits_balance - 1,
      pack_credits = case when v_from_pack then pack_credits - 1 else pack_credits end
  where id = v_org_id;
  insert into credits_ledger
    (organization_id, delta, reason, related_content_item_id, balance_after, generation_run)
  values
    (v_org_id, -1,
     case when v_from_pack then 'video_generation_reserved_pack' else 'video_generation_reserved' end,
     p_content_item_id, v_balance - 1, v_completed + 1);
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
  v_completed integer;
  v_held integer;
  v_justified integer;
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

  select completed_generations into v_completed
  from content_items where id = p_content_item_id;

  select coalesce(-sum(delta), 0) into v_held
  from credits_ledger
  where related_content_item_id = p_content_item_id
    and reason in (
      'video_generation_reserved', 'video_generation_refund',
      'video_generation_reserved_pack', 'video_generation_refund_pack'
    );

  v_justified := case when v_completed = 0 then 0 else greatest(1, v_completed - 1) end;
  if v_held <= v_justified then return false; end if;

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
      (organization_id, delta, reason, related_content_item_id, balance_after, generation_run)
    values
      (v_org_id, 1, 'video_generation_refund_pack', p_content_item_id, v_balance + 1, v_completed + 1);
  else
    update organizations set credits_balance = credits_balance + 1 where id = v_org_id;
    insert into credits_ledger
      (organization_id, delta, reason, related_content_item_id, balance_after, generation_run)
    values
      (v_org_id, 1, 'video_generation_refund', p_content_item_id, v_balance + 1, v_completed + 1);
  end if;
  return true;
end;
$$;

-- Appelé par le worker quand un run se termine avec succès : c'est ce qui fait
-- avancer la politique (retouche gratuite, puis payant).
create or replace function public.mark_generation_completed(p_content_item_id uuid)
returns integer
language sql
security definer
set search_path = public
as $$
  update content_items
  set completed_generations = completed_generations + 1
  where id = p_content_item_id
  returning completed_generations;
$$;

revoke all on function public.reserve_generation_credit(uuid) from public, anon, authenticated;
revoke all on function public.refund_generation_credit(uuid) from public, anon, authenticated;
revoke all on function public.mark_generation_completed(uuid) from public, anon, authenticated;
grant execute on function public.reserve_generation_credit(uuid) to service_role;
grant execute on function public.refund_generation_credit(uuid) to service_role;
grant execute on function public.mark_generation_completed(uuid) to service_role;
