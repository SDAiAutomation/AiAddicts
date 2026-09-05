-- Revue de sécurité (2026-09-05) : engine.repo.charge_generation_credit()
-- faisait un lecture-puis-écriture applicatif (select credits_balance ->
-- calcul -> update), non atomique. Deux workers traitant deux content_items
-- de la même organisation en parallèle (ex: deux runs GitHub Actions qui se
-- chevauchent) pouvaient lire le même solde de départ et perdre un
-- décompte. Verrou de ligne (`for update`) + logique de décompte dans une
-- seule transaction côté Postgres : un décompte concurrent attend son tour
-- au lieu de travailler sur une valeur périmée.

create or replace function public.charge_generation_credit(p_content_item_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_org_id uuid;
  v_plan text;
  v_old_balance integer;
  v_new_balance integer;
begin
  select a.organization_id into v_org_id
  from content_items ci
  join accounts a on a.id = ci.account_id
  where ci.id = p_content_item_id;

  if v_org_id is null then
    return;
  end if;

  -- Verrouille la ligne organisation pour la durée de la transaction : un
  -- second appel concurrent (autre content_item, même org) attend ici que
  -- celui-ci commit, au lieu de lire un credits_balance déjà obsolète.
  select plan, credits_balance into v_plan, v_old_balance
  from organizations
  where id = v_org_id
  for update;

  if v_plan = 'business' then
    return; -- illimité par design, pas de décompte
  end if;

  v_new_balance := greatest(0, v_old_balance - 1);

  update organizations set credits_balance = v_new_balance where id = v_org_id;

  insert into credits_ledger (organization_id, delta, reason, related_content_item_id, balance_after)
  values (v_org_id, v_new_balance - v_old_balance, 'video_generated', p_content_item_id, v_new_balance);
end;
$$;

-- Réservée au worker (service_role) — même logique d'accès que le reste du
-- décompte de crédits, jamais appelable depuis un client authentifié normal.
revoke all on function public.charge_generation_credit(uuid) from public, anon, authenticated;
grant execute on function public.charge_generation_credit(uuid) to service_role;
