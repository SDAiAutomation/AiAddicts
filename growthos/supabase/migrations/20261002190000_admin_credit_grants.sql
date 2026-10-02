-- Administration de la plateforme : ajout de crédits tracé.
--
-- `admin_actions` : journal d'audit des actions d'administration. RLS activée SANS policy et tous droits retirés à
-- anon/authenticated : seul service_role (donc le serveur Faceloop, après contrôle de la liste blanche
-- ADMIN_USER_IDS) peut le lire ou y écrire. Les membres d'une organisation ne voient jamais l'identité de l'admin.
--
-- `admin_grant_credits` : solde + journal des crédits + audit dans UNE transaction. Exécutable par service_role
-- uniquement (jamais par un utilisateur connecté, même owner). Montant borné 1..500, motif obligatoire.
-- Additive : aucune ligne existante modifiée.

create table if not exists public.admin_actions (
  id uuid primary key default gen_random_uuid(),
  actor_user_id uuid not null,
  action text not null,
  organization_id uuid references public.organizations(id) on delete set null,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists admin_actions_created_idx on public.admin_actions (created_at desc);

alter table public.admin_actions enable row level security;
revoke all on public.admin_actions from anon, authenticated;

create or replace function public.admin_grant_credits(p_org uuid, p_amount integer, p_note text, p_actor uuid)
returns table (balance_after integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  new_balance integer;
  clean_note text := left(btrim(coalesce(p_note, '')), 200);
begin
  if p_amount is null or p_amount < 1 or p_amount > 500 then
    raise exception 'invalid_amount';
  end if;
  if p_actor is null then
    raise exception 'actor_required';
  end if;
  if clean_note = '' then
    raise exception 'note_required';
  end if;

  update public.organizations
     set credits_balance = credits_balance + p_amount
   where id = p_org
  returning credits_balance into new_balance;
  if not found then
    raise exception 'organization_not_found';
  end if;

  insert into public.credits_ledger (organization_id, delta, reason, balance_after)
  values (p_org, p_amount, 'manual_grant', new_balance);

  insert into public.admin_actions (actor_user_id, action, organization_id, detail)
  values (p_actor, 'grant_credits', p_org, jsonb_build_object('amount', p_amount, 'note', clean_note, 'balance_after', new_balance));

  return query select new_balance;
end;
$$;

revoke all on function public.admin_grant_credits(uuid, integer, text, uuid) from public, anon, authenticated;
grant execute on function public.admin_grant_credits(uuid, integer, text, uuid) to service_role;
