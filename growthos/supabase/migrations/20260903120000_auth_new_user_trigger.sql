-- Inscription self-serve : à chaque création dans auth.users, provisionner
-- automatiquement le profil + une organisation personnelle + le rôle owner.
-- Supprime le besoin de scripts/backfill_membership.py pour les nouveaux users.
-- (Les users créés avant ce trigger — ex. le compte owner initial — gardent
-- leur rattachement fait à la main / via backfill.)

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  display_name text;
  new_org_id uuid;
begin
  display_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'full_name'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), ''),
    split_part(new.email, '@', 1)
  );

  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, display_name)
  on conflict (id) do nothing;

  insert into public.organizations (name)
  values (display_name || ' — workspace')
  returning id into new_org_id;

  insert into public.organization_members (organization_id, user_id, role)
  values (new_org_id, new.id, 'owner')
  on conflict (organization_id, user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
