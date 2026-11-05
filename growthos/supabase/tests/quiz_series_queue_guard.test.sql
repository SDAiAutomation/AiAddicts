-- Test statique (pgTAP) de 20261105183848_quiz_series_queue_guard.sql. NON EXÉCUTÉ (pas de Postgres local dans la session).
-- Le comportement (42501 avec un jeton utilisateur) se teste en staging : voir l'en-tête de la migration.
begin;
select plan(3);

select ok(pg_get_functiondef('public.queue_due_series_episodes(uuid)'::regprocedure) like '%<> ''quiz''%',
  'the cron never queues quiz episodes');
select ok(pg_get_functiondef('public.guard_content_items_internal_columns()'::regprocedure) like '%s.content_format = ''quiz''%',
  'the guard recognises a series quiz from the series, not only from the editable script');
select ok(not has_function_privilege('authenticated', 'public.guard_content_items_internal_columns()', 'execute'),
  'the guard function is not callable by clients');

select * from finish();
rollback;
