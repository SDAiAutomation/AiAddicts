-- Horloge fiable : Supabase appelle /api/cron/tick toutes les 10 minutes.
--
-- Les exécutions planifiées de GitHub Actions sont trop irrégulières (aucune
-- entre 14:47 et 18:04 UTC le 2026-09-25 : un montage AutoEdit est resté 2 h
-- en file, les épisodes de série dus attendaient). La route web génère les
-- épisodes dus, réveille le worker GitHub (workflow_dispatch) s'il reste du
-- travail et lance le contrôle de santé une fois par heure. Les schedules
-- GitHub restent en place comme filet de secours.
--
-- Le secret d'appel est la valeur de CRON_SECRET (déjà utilisée par les
-- autres routes /api/cron/*), rangée dans Supabase Vault sous le nom
-- 'cron_secret'. Elle n'est jamais écrite dans ce fichier : à créer une fois
-- depuis le SQL Editor —
--   select vault.create_secret('<valeur de CRON_SECRET>', 'cron_secret');
-- Tant qu'elle n'existe pas, le job ne fait rien.

create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.unschedule('faceloop-tick')
where exists (select 1 from cron.job where jobname = 'faceloop-tick');

select cron.schedule(
  'faceloop-tick',
  '*/10 * * * *',
  $job$
  select net.http_post(
    url := 'https://www.faceloop.app/api/cron/tick',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || secret.decrypted_secret
    ),
    body := '{}'::jsonb,
    -- La génération d'un épisode (script OpenAI) peut prendre ~1 min.
    timeout_milliseconds := 120000
  )
  from vault.decrypted_secrets secret
  where secret.name = 'cron_secret';
  $job$
);
