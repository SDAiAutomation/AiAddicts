-- Quiz 50 : exports verticaux par chapitre (Shorts), file de jobs tenue par le worker.
--
-- Additive et rejouable : aucune colonne existante n'est modifiée. Une ligne = un chapitre d'une vidéo.
-- * Lecture : membres de l'organisation du contenu (RLS), sans les chemins de stockage (colonne réservée au serveur).
-- * Écriture : uniquement via request_quiz_chapter_export() (rôle owner/strategist/editor, contrôles de forme et
--   idempotence) ou via service_role (worker). Aucun INSERT/UPDATE/DELETE direct pour `authenticated`.
-- * Stockage : fichiers sous `<content_item_id>/shorts/v<n>/quiz_<niveau>[_partN].mp4` dans le bucket privé
--   `content-videos` ; le site signe un accès temporaire APRÈS avoir lu la ligne sous RLS.
-- Ne pas appliquer en production sans validation en préproduction (voir docs/LONG_QUIZ_50_DELIVERY_PLAN.md).

create table if not exists public.quiz_chapter_exports (
  id uuid primary key default gen_random_uuid(),
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  chapter smallint not null check (chapter between 1 and 5),
  status text not null default 'pending' check (status in ('pending', 'processing', 'ready', 'failed')),
  attempts smallint not null default 0 check (attempts between 0 and 5),
  source_version_id uuid references public.content_versions(id) on delete set null,
  -- Sorties visibles : [{file, part, parts, first_question, last_question, duration, width, height, bytes, short_eligible}]
  outputs jsonb not null default '[]'::jsonb check (jsonb_typeof(outputs) = 'array' and jsonb_array_length(outputs) <= 10),
  -- Réservé au serveur : {file: chemin de stockage}. Jamais lisible par `authenticated`.
  storage_paths jsonb not null default '{}'::jsonb,
  error text check (error is null or length(error) <= 500),
  requested_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (content_item_id, chapter)
);

create index if not exists quiz_chapter_exports_queue_idx
  on public.quiz_chapter_exports (created_at) where status in ('pending', 'processing');

alter table public.quiz_chapter_exports enable row level security;

drop policy if exists "quiz_chapter_exports_member_select" on public.quiz_chapter_exports;
create policy "quiz_chapter_exports_member_select" on public.quiz_chapter_exports for select
  using (exists (
    select 1 from public.content_items ci
    where ci.id = content_item_id
      and internal.account_organization_id(ci.account_id) in (select internal.current_user_org_ids())
  ));

revoke all on table public.quiz_chapter_exports from anon, authenticated;
grant select (id, content_item_id, chapter, status, attempts, source_version_id, outputs, error, requested_by, created_at, updated_at)
  on table public.quiz_chapter_exports to authenticated;
grant all on table public.quiz_chapter_exports to service_role;

-- Demande (ou relance) d'exports. Idempotente :
--   pending/processing -> inchangé ; ready sur la même version -> inchangé ;
--   ready sur une ancienne version -> remis en file (compteur remis à zéro) ;
--   failed -> remis en file, 5 essais maximum par chapitre et par version.
create or replace function public.request_quiz_chapter_export(p_content_item_id uuid, p_chapters integer[])
returns setof public.quiz_chapter_exports
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item public.content_items%rowtype;
  v_chapter integer;
  v_row public.quiz_chapter_exports%rowtype;
begin
  select * into v_item from public.content_items where id = p_content_item_id;
  if not found then
    raise exception 'content item not found' using errcode = 'P0002';
  end if;
  if auth.role() <> 'service_role'
     and not internal.has_org_role(internal.account_organization_id(v_item.account_id), array['owner', 'strategist', 'editor']) then
    raise exception 'forbidden' using errcode = '42501';
  end if;
  if v_item.status not in ('video', 'quality_check', 'published') or v_item.video_url is null then
    raise exception 'the full video must be rendered first' using errcode = '22023';
  end if;
  if coalesce(v_item.script->>'content_format', '') <> 'quiz'
     or coalesce(v_item.script->'quiz'->>'chapter_mode', '') <> 'five_levels'
     or coalesce(v_item.script->'quiz'->>'presentation', '') <> 'motion' then
    raise exception 'chapter exports need a five-level Motion quiz' using errcode = '22023';
  end if;
  if p_chapters is null or cardinality(p_chapters) not between 1 and 5 then
    raise exception 'invalid chapters' using errcode = '22023';
  end if;

  foreach v_chapter in array p_chapters loop
    if v_chapter is null or v_chapter not between 1 and 5 then
      raise exception 'invalid chapter' using errcode = '22023';
    end if;
    insert into public.quiz_chapter_exports (content_item_id, chapter, source_version_id, requested_by)
    values (p_content_item_id, v_chapter, v_item.current_version_id, auth.uid())
    on conflict (content_item_id, chapter) do update set
      status = 'pending', source_version_id = excluded.source_version_id, requested_by = excluded.requested_by,
      attempts = case when quiz_chapter_exports.status = 'ready' then 0 else quiz_chapter_exports.attempts end,
      outputs = '[]'::jsonb, storage_paths = '{}'::jsonb, error = null, updated_at = now()
    where (quiz_chapter_exports.status = 'failed' and quiz_chapter_exports.attempts < 5)
       or (quiz_chapter_exports.status = 'ready'
           and quiz_chapter_exports.source_version_id is distinct from excluded.source_version_id);
  end loop;

  return query select * from public.quiz_chapter_exports
    where content_item_id = p_content_item_id and chapter = any(p_chapters) order by chapter;
end;
$$;

revoke execute on function public.request_quiz_chapter_export(uuid, integer[]) from public, anon;
grant execute on function public.request_quiz_chapter_export(uuid, integer[]) to authenticated, service_role;

-- Réclamation par le worker (service_role seulement) : un job à la fois, `skip locked` pour plusieurs workers ;
-- un job 'processing' abandonné depuis plus d'une heure repart en file (ou échoue après 5 essais).
create or replace function public.claim_quiz_chapter_export()
returns setof public.quiz_chapter_exports
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id uuid;
begin
  update public.quiz_chapter_exports
     set status = case when attempts + 1 >= 5 then 'failed' else 'pending' end,
         attempts = attempts + 1,
         error = case when attempts + 1 >= 5 then 'Le rendu a été interrompu trop de fois.' else error end,
         updated_at = now()
   where status = 'processing' and updated_at < now() - interval '1 hour';

  select id into v_id from public.quiz_chapter_exports
   where status = 'pending' order by created_at for update skip locked limit 1;
  if v_id is null then
    return;
  end if;
  return query update public.quiz_chapter_exports
     set status = 'processing', attempts = attempts + 1, updated_at = now()
   where id = v_id returning *;
end;
$$;

revoke execute on function public.claim_quiz_chapter_export() from public, anon, authenticated;
grant execute on function public.claim_quiz_chapter_export() to service_role;

-- Cohérence du format : un quiz en cinq niveaux est une série « long » de 50 questions, sans exception.
alter table public.series drop constraint if exists series_quiz_chapter_mode_shape;
alter table public.series add constraint series_quiz_chapter_mode_shape check (
  quiz_config is null
  or coalesce(quiz_config->>'chapter_mode', 'legacy') = 'legacy'
  or (quiz_config->>'chapter_mode' = 'five_levels'
      and quiz_config->>'recipe' = 'long'
      and (quiz_config->>'question_count')::integer = 50
      and quiz_config->>'difficulty' = 'progressive')
) not valid;
alter table public.series validate constraint series_quiz_chapter_mode_shape;
