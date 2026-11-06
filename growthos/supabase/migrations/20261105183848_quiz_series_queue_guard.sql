-- Épisodes Quiz de série : jamais de mise en file de rendu sans vérification des réponses.
--
-- MIGRATION MIROIR : déjà appliquée à la main sur le projet « growthos » le 2026-11-05 (version 20261105183848, via
-- apply_migration). Ce fichier aligne le dépôt sur la base ; il est idempotent (create or replace). Source : growthos-web
-- docs/sql/2026-11-05_quiz_series_queue_guard.sql (PR #188 puis #189). Le test PATCH avec un jeton utilisateur
-- (42501 sur status='queued' d'un quiz de série, y compris après réécriture du script) reste à faire.
--
--   A. queue_due_series_episodes ignore les quiz (approuvés par une personne).
--   B. guard_content_items_internal_columns refuse à un client direct le passage à 'queued' d'un quiz de série ;
--      le quiz est reconnu par series.content_format (le script, réécrivable par le client, n'est testé qu'en plus).
--      Le site écrit ce passage avec le client de service après contrôle des reçus (approveSeriesEpisode, queueGeneration).
--
-- Retour arrière : réappliquer 20260919145043_series_editorial_calendar (A) et 20261011184932_content_items_guard_internal_columns (B).

create or replace function public.queue_due_series_episodes(p_series_id uuid default null)
returns setof uuid
language sql
security definer
set search_path = public
as $$
  update public.content_items item
  set status = 'queued',
      editorial_status = 'locked',
      error = null,
      updated_at = now()
  from public.series s
  where item.series_id = s.id
    and s.status = 'active'
    and (p_series_id is null or item.series_id = p_series_id)
    and item.status = 'script'
    and item.editorial_status in ('draft', 'approved')
    and item.generation_deadline <= now()
    and coalesce(item.script->>'content_format', '') <> 'quiz'
  returning item.id;
$$;

create or replace function public.guard_content_items_internal_columns()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if current_user not in ('authenticated', 'anon') then
    return new;
  end if;

  if tg_op = 'INSERT' then
    if new.status not in ('idea', 'script')
       or new.video_url is not null
       or new.original_video_url is not null
       or new.poster_url is not null
       or new.completed_generations <> 0
       or new.generation_cost_report is not null
       or new.generation_deadline is not null
       or new.generation_step is not null
       or new.image_generation_report is not null
       or new.originality_report is not null
       or new.quality_flags <> '[]'::jsonb
       or new.quality_score is not null
       or new.error is not null
       or new.current_version_id is not null
       or new.video_script_version is not null
       or new.script_version <> 1
       or new.youtube_video_id is not null
       or new.youtube_privacy_status is not null
       or new.series_id is not null
       or new.episode_number is not null
       or new.trim_status is not null
       or new.trim_error is not null
       or new.trim_start <> 0
       or new.trim_end is not null
       or (new.requested_by is not null and new.requested_by is distinct from auth.uid())
    then
      raise exception 'content_items: champ interne reserve au serveur'
        using errcode = '42501';
    end if;
    return new;
  end if;

  if new.video_url is distinct from old.video_url
     or new.original_video_url is distinct from old.original_video_url
     or new.poster_url is distinct from old.poster_url
     or new.completed_generations is distinct from old.completed_generations
     or new.generation_cost_report is distinct from old.generation_cost_report
     or new.generation_deadline is distinct from old.generation_deadline
     or new.generation_step is distinct from old.generation_step
     or new.image_generation_report is distinct from old.image_generation_report
     or new.originality_report is distinct from old.originality_report
     or new.quality_flags is distinct from old.quality_flags
     or new.quality_score is distinct from old.quality_score
     or new.current_version_id is distinct from old.current_version_id
     or new.video_script_version is distinct from old.video_script_version
     or new.script_version is distinct from old.script_version
     or new.youtube_video_id is distinct from old.youtube_video_id
     or new.youtube_privacy_status is distinct from old.youtube_privacy_status
     or new.series_id is distinct from old.series_id
     or new.episode_number is distinct from old.episode_number
  then
    raise exception 'content_items: champ interne reserve au serveur'
      using errcode = '42501';
  end if;

  -- AJOUT : un episode Quiz de serie ne passe en file que par le serveur, apres controle des recus de verification.
  if new.status is distinct from old.status
     and new.status = 'queued'
     and new.series_id is not null
     and (
       exists (select 1 from public.series s where s.id = new.series_id and s.content_format = 'quiz')
       or coalesce(old.script->>'content_format', '') = 'quiz'
       or coalesce(new.script->>'content_format', '') = 'quiz'
     )
  then
    raise exception 'content_items: mise en file d''un quiz de serie reservee au serveur'
      using errcode = '42501';
  end if;

  if (new.status is distinct from old.status and new.status not in ('idea', 'script', 'queued', 'published'))
     or (new.error is distinct from old.error and new.error is not null)
     or (new.trim_status is distinct from old.trim_status and new.trim_status is distinct from 'pending')
     or (new.trim_error is distinct from old.trim_error and new.trim_error is not null)
     or ((new.trim_start is distinct from old.trim_start or new.trim_end is distinct from old.trim_end)
         and (new.trim_start < 0 or (new.trim_end is not null and new.trim_end <= new.trim_start)))
     or (new.requested_by is distinct from old.requested_by
         and new.requested_by is not null and new.requested_by is distinct from auth.uid())
  then
    raise exception 'content_items: valeur non autorisee pour un client'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke all on function public.guard_content_items_internal_columns() from public, anon, authenticated;
