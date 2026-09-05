-- Étape "Configuration" (niche/style visuel/voix) avant le formulaire de
-- script — voir growthos-web content/content-config.tsx. La niche devient
-- une vraie entité réutilisable par organisation (comme `accounts`) au lieu
-- d'un texte libre ressaisi à chaque script.

create table niches (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id) on delete cascade,
  name text not null,
  description text,
  default_tone text,
  created_at timestamptz not null default now(),
  unique (organization_id, name)
);
create index on niches (organization_id);

alter table niches enable row level security;

create policy "niches_member_select" on niches for select
  using (organization_id in (select internal.current_user_org_ids()));
-- Insert ouvert aux mêmes rôles que la création de contenu (owner/strategist/
-- editor) : la niche se crée à la volée depuis le combobox du formulaire de
-- script, pas seulement depuis une page de gestion des comptes.
create policy "niches_insert_content_roles" on niches for insert
  with check (internal.has_org_role(organization_id, array['owner','strategist','editor']));
create policy "niches_update_roles" on niches for update
  using (internal.has_org_role(organization_id, array['owner','strategist']));
create policy "niches_delete_owner" on niches for delete
  using (internal.has_org_role(organization_id, array['owner']));

-- Backfill : les organisations déjà existantes (créées avant cette
-- migration) n'ont jamais eu de niches — leur poser le même catalogue de
-- départ que ce que handle_new_user() donnera désormais aux nouvelles.
insert into niches (organization_id, name, description, default_tone)
select o.id, n.name, n.description, n.default_tone
from organizations o
cross join (values
  ('Prospection B2B', 'Conseils et retours d''expérience pour améliorer sa prospection commerciale.', 'direct et percutant'),
  ('Finance perso', 'Conseils pratiques pour gérer son argent, épargner et investir.', 'posé et pédagogique'),
  ('Histoires pour enfants', 'Récits courts et éducatifs pensés pour un jeune public.', 'chaleureux et imagé'),
  ('Développement personnel', 'Habitudes, mindset et méthodes pour progresser au quotidien.', 'inspirant et bienveillant'),
  ('Actualité / débrief', 'Résumés et analyses de l''actualité récente.', 'informatif et posé')
) as n(name, description, default_tone)
where not exists (select 1 from niches where niches.organization_id = o.id);

-- Même catalogue de départ pour toute organisation créée à partir de
-- maintenant (self-serve signup, voir auth_new_user_trigger.sql).
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

  insert into public.niches (organization_id, name, description, default_tone)
  values
    (new_org_id, 'Prospection B2B', 'Conseils et retours d''expérience pour améliorer sa prospection commerciale.', 'direct et percutant'),
    (new_org_id, 'Finance perso', 'Conseils pratiques pour gérer son argent, épargner et investir.', 'posé et pédagogique'),
    (new_org_id, 'Histoires pour enfants', 'Récits courts et éducatifs pensés pour un jeune public.', 'chaleureux et imagé'),
    (new_org_id, 'Développement personnel', 'Habitudes, mindset et méthodes pour progresser au quotidien.', 'inspirant et bienveillant'),
    (new_org_id, 'Actualité / débrief', 'Résumés et analyses de l''actualité récente.', 'informatif et posé');

  return new;
end;
$$;
