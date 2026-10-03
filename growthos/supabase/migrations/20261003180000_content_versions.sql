-- Lot L2 (audit bible 2026-10-03) : versions immuables et retour arrière.
--
-- Avant : une régénération ou un rognage réécrivait `<id>.mp4` en place, sans
-- retour possible, et la publication visait le content_item, pas un fichier.
-- Désormais chaque rendu (génération, rognage) crée une version dont le
-- fichier vit sous un chemin immuable `<id>/v<n>.mp4` ; `content_items`
-- pointe vers la version courante et, après publication, vers la version
-- exacte publiée.

create table if not exists public.content_versions (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  version_number integer not null check (version_number >= 1),
  kind text not null check (kind in ('generation', 'trim')),
  video_url text not null,
  poster_url text,
  captions_url text,
  script jsonb,
  duration_seconds numeric,
  created_at timestamptz not null default now(),
  unique (content_item_id, version_number)
);

create index if not exists content_versions_item_idx
  on public.content_versions (content_item_id, version_number desc);

alter table public.content_versions enable row level security;

create policy "content_versions_member_select" on public.content_versions for select
  using (exists (
    select 1 from public.content_items ci
    where ci.id = content_item_id
      and public.account_organization_id(ci.account_id) in (select public.current_user_org_ids())
  ));

revoke all on table public.content_versions from anon, authenticated;
grant select on table public.content_versions to authenticated;
grant all on table public.content_versions to service_role;

alter table public.content_items
  add column if not exists current_version_id uuid references public.content_versions(id) on delete set null,
  add column if not exists published_version_id uuid references public.content_versions(id) on delete set null;

-- Retour arrière : la version choisie redevient la vidéo courante. Aucun
-- fichier n'est copié ni régénéré (les versions sont immuables), donc gratuit.
-- Le script de la version est restauré avec elle pour rester cohérent avec
-- la vidéo. Les rognages en cours et l'archive d'origine sont oubliés (ils
-- se rapportaient à la vidéo précédente).
create or replace function public.restore_content_version(p_content_item_id uuid, p_version_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_account uuid;
  v_ver content_versions%rowtype;
begin
  select account_id into v_account from content_items where id = p_content_item_id;
  if v_account is null then return false; end if;

  if auth.role() <> 'service_role'
     and not has_org_role(account_organization_id(v_account), array['owner','strategist','editor']) then
    raise exception 'forbidden' using errcode = '42501';
  end if;

  select * into v_ver from content_versions
  where id = p_version_id and content_item_id = p_content_item_id;
  if not found then return false; end if;

  update content_items set
    video_url = v_ver.video_url,
    poster_url = coalesce(v_ver.poster_url, poster_url),
    script = coalesce(v_ver.script, script),
    current_version_id = v_ver.id,
    original_video_url = null,
    trim_start = 0,
    trim_end = null,
    trim_status = null,
    updated_at = now()
  where id = p_content_item_id
    and status in ('video', 'quality_check', 'published')
    and coalesce(trim_status, '') not in ('pending', 'processing');
  return found;
end;
$$;

revoke execute on function public.restore_content_version(uuid, uuid) from public, anon;
grant execute on function public.restore_content_version(uuid, uuid) to authenticated, service_role;
