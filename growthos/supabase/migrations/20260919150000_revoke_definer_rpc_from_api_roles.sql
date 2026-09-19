-- Sur Supabase, anon/authenticated reçoivent EXECUTE explicitement (privilèges
-- par défaut) : `revoke ... from public` ne suffit pas. Ces fonctions ne sont
-- appelées que par le client service_role (cron, worker) ou par des triggers ;
-- aucune raison de les exposer en RPC. Le privilège EXECUTE n'est vérifié qu'à
-- la création d'un trigger, pas à son déclenchement : les triggers continuent.
revoke execute on function public.claim_content_publication_job() from anon, authenticated;
revoke execute on function public.claim_series_run(uuid, timestamptz, timestamptz) from anon, authenticated;
revoke execute on function public.queue_due_series_episodes(uuid) from anon, authenticated;
revoke execute on function public.invalidate_series_episode_on_script_change() from anon, authenticated;
revoke execute on function public.queue_series_publication() from anon, authenticated;
revoke execute on function public.record_rendered_script_version() from anon, authenticated;

-- handle_new_user() n'est déclenchée que par le trigger sur auth.users ; son
-- EXECUTE venait aussi du rôle PUBLIC, d'où anon/authenticated l'héritaient.
revoke execute on function public.handle_new_user() from public, anon, authenticated;
