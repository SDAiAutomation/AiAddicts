-- Garde des colonnes internes de content_items.
--
-- Probleme : le role `authenticated` pouvait ecrire (INSERT/UPDATE) presque toutes les colonnes de
-- content_items avec la cle publique et sa session. Il pouvait donc modifier des champs que seul le
-- serveur doit ecrire : les URL de resultat (video_url, original_video_url, poster_url), le compteur
-- completed_generations qui sert a la politique de credits, les rapports de cout et de qualite, les
-- versions, etc.
--
-- Principe : un declencheur BEFORE INSERT OR UPDATE ne controle que les appels directs d'un client
-- connecte (current_user = authenticated ou anon, c'est-a-dire PostgREST avec la session de
-- l'utilisateur). service_role, postgres et les fonctions SECURITY DEFINER (current_user = leur
-- proprietaire) ne sont pas touches : worker, crons, restore_content_version, mark_generation_completed,
-- queue_due_series_episodes continuent de fonctionner. Le declencheur s'appelle a0_... pour s'executer
-- AVANT les declencheurs existants, qui modifient legitimement NEW (script_version, status, video_url...)
-- lors d'un changement de script : seule la requete telle que le client l'a envoyee est jugee.
--
-- Colonnes que le site ecrit legitimement avec la session de l'utilisateur et qui restent libres :
-- title, script, recommendation_report, story_features, editorial_status, script_score, score_details (ecrits
-- par updateScript pour les episodes de serie), scheduled_for, published_at, published_version_id, account_id,
-- updated_at, tiktok_publish_id/status/error. Risque residuel assume : script_score et score_details restent
-- falsifiables par un utilisateur (affichage et rapport consultatif) ; a fermer en deplacant cette ecriture cote serveur. Contraintes de valeur :
-- status (idea, script, queued, published), error (effacement seulement), trim_status (pending
-- seulement), trim_error (effacement seulement), trim_start/trim_end (bornes), requested_by (soi-meme).
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

drop trigger if exists a0_guard_content_items_internal_columns on public.content_items;
create trigger a0_guard_content_items_internal_columns
  before insert or update on public.content_items
  for each row execute function public.guard_content_items_internal_columns();
