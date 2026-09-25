-- AutoEdit : montages privés + rétention.
--
-- Avant : le montage rendu partait dans le bucket PUBLIC des vidéos générées
-- (content-videos) — lisible sans limite de temps par quiconque obtient
-- l'URL. Or ce sont des vidéos envoyées par les utilisateurs.
--
-- Après :
-- - bucket privé autoedit-results, chemin <organization_id>/<job_id>/result.mp4
--   (+ poster.jpg). Aucune policy : seul le service_role (worker, API web)
--   y accède ; l'API web renvoie des URL signées temporaires ;
-- - result_video_path / result_poster_path : chemins dans ce bucket (les
--   colonnes video_url / poster_url restent pour compatibilité, plus écrites) ;
-- - expires_at : date de suppression prévue (posée par le worker à la fin du
--   job, AUTOEDIT_RETENTION_DAYS) ; purged_at : sources et rendus supprimés
--   (purge_autoedit.py, lancé chaque jour).

alter table public.autoedit_jobs
  add column if not exists result_video_path text,
  add column if not exists result_poster_path text,
  add column if not exists expires_at timestamptz,
  add column if not exists purged_at timestamptz;

create index if not exists autoedit_jobs_purge_idx
  on public.autoedit_jobs (expires_at) where purged_at is null;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('autoedit-results', 'autoedit-results', false, 524288000, array['video/mp4', 'image/jpeg'])
on conflict (id) do nothing;

comment on column public.autoedit_jobs.result_video_path is
  'Montage rendu dans le bucket privé autoedit-results. Lu via URL signée temporaire (API web), jamais public.';
comment on column public.autoedit_jobs.expires_at is
  'Suppression prévue de la source et des rendus (purge_autoedit.py). null = pas encore terminé.';
comment on column public.autoedit_jobs.purged_at is
  'Source et rendus supprimés du stockage à cette date ; le job reste comme historique.';
