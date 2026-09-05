-- Décision produit (2026-09-05) : un nouvel inscrit doit pouvoir tester le
-- produit avant de payer. `handle_new_user()` créait déjà l'organisation
-- perso avec `credits_balance` par défaut à 0 (colonne définie dans
-- core_tenancy.sql) — aucun plan n'étant gratuit (Starter = 19€/mois), un
-- inscrit ne pouvait jamais générer une seule vidéo sans payer d'abord.
--
-- 3 crédits d'essai, journalisés dans credits_ledger comme toute variation
-- de solde (jusqu'ici cette table existait mais n'était jamais écrite).

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  display_name text;
  new_org_id uuid;
  trial_credits constant integer := 3;
begin
  display_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'full_name'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), ''),
    split_part(new.email, '@', 1)
  );

  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, display_name)
  on conflict (id) do nothing;

  insert into public.organizations (name, credits_balance)
  values (display_name || ' — workspace', trial_credits)
  returning id into new_org_id;

  insert into public.organization_members (organization_id, user_id, role)
  values (new_org_id, new.id, 'owner')
  on conflict (organization_id, user_id) do nothing;

  insert into public.credits_ledger (organization_id, delta, reason, balance_after)
  values (new_org_id, trial_credits, 'signup_trial', trial_credits);

  return new;
end;
$$;
