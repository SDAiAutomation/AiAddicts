-- Story Studio : sauvegarde / reprise des projets d'histoire (brouillons).
--
-- Additif et rejouable : une seule table, aucune donnée existante touchée. Un projet
-- appartient à une organisation ; il ne contient que le storyboard édité par
-- l'utilisateur (personnages + voix choisies + scènes). AUCUNE génération audio/vidéo
-- n'est déclenchée par cette table : `status` ne connaît que le brouillon tant que
-- le pipeline de rendu n'est pas branché (valeurs ajoutées alors par migration).
--
-- Lecture : membres de l'organisation. Écriture : owner / strategist / editor.
-- `organization_id` et `created_by` ne sont pas falsifiables depuis le client.

create table if not exists public.story_projects (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid references auth.users (id) on delete set null,
  title text not null default '' check (char_length(title) <= 120),
  status text not null default 'draft' check (status in ('draft')),
  -- [{ "id": "neo", "name": "Néo", "voice_id": "..." }], 0 à 8 personnages
  characters jsonb not null default '[]'::jsonb
    check (jsonb_typeof(characters) = 'array' and jsonb_array_length(characters) <= 8 and pg_column_size(characters) <= 16384),
  -- [{ "id": "shot_01", "speaker_id": "neo", "dialogue": "...", "duration_s": 5 }], 0 à 30 scènes
  shots jsonb not null default '[]'::jsonb
    check (jsonb_typeof(shots) = 'array' and jsonb_array_length(shots) <= 30 and pg_column_size(shots) <= 131072),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists story_projects_org_updated_idx
  on public.story_projects (organization_id, updated_at desc);

create or replace function internal.touch_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
revoke execute on function internal.touch_updated_at() from public, anon, authenticated;

drop trigger if exists story_projects_touch_updated_at on public.story_projects;
create trigger story_projects_touch_updated_at
  before update on public.story_projects
  for each row execute function internal.touch_updated_at();

create or replace function public.guard_story_projects_owner()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if current_user not in ('authenticated', 'anon') then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.created_by := auth.uid();
  else
    new.created_by := old.created_by;
    new.organization_id := old.organization_id;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_story_projects_owner() from public;

drop trigger if exists a0_guard_story_projects_owner on public.story_projects;
create trigger a0_guard_story_projects_owner
  before insert or update on public.story_projects
  for each row execute function public.guard_story_projects_owner();

alter table public.story_projects enable row level security;

drop policy if exists "story_projects_member_select" on public.story_projects;
create policy "story_projects_member_select" on public.story_projects for select
  using (organization_id in (select internal.current_user_org_ids()));

drop policy if exists "story_projects_editor_write" on public.story_projects;
create policy "story_projects_editor_write" on public.story_projects for all
  using (internal.has_org_role(organization_id, array['owner', 'strategist', 'editor']))
  with check (internal.has_org_role(organization_id, array['owner', 'strategist', 'editor']));

revoke all on table public.story_projects from anon, authenticated;
grant select, insert, update, delete on table public.story_projects to authenticated;
grant all on table public.story_projects to service_role;
