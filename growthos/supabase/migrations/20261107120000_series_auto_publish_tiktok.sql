-- Publication automatique des séries : accepter 'tiktok' en plus de 'youtube' au niveau du schéma.
--
-- Objet : élargir deux contraintes CHECK à ['youtube','tiktok'] :
--   - public.series.auto_publish_platforms (tableau, <@) ;
--   - public.content_publication_jobs.platform.
-- Aucune valeur par défaut, aucune donnée, aucune fonction, aucun trigger, aucun grant ni aucune politique RLS ne change.
-- Lecture / écriture autorisées : inchangées (series : membres via RLS existante ; content_publication_jobs : SELECT
--   membres de l'organisation, écriture service_role et trigger security definer queue_series_publication).
-- Stockage : aucun.
--
-- ATTENTION PRODUIT : la route cron growthos-web /api/cron/auto-publish ne traite que YouTube. Un job 'tiktok' créé par
-- queue_series_publication (série avec 'tiktok' + jeton TikTok connecté) serait réclamé puis marqué 'failed'
-- (« Plateforme non prise en charge par la publication automatique »). Les règles TikTok Direct Post (visibilité choisie
-- explicitement, consentement avant envoi) et l'app non auditée (privé seulement) restent à trancher par le propriétaire.
-- Ne pas appliquer en production sans cette décision ni sans validation en préproduction.
--
-- Rejouable : les anciennes contraintes (noms générés par Postgres) sont retrouvées par colonne et remplacées par une
-- contrainte nommée ; un second passage ne fait rien.
--
-- Retour arrière (seulement si aucune ligne ne contient 'tiktok') :
--   alter table public.series drop constraint series_auto_publish_platforms_allowed,
--     add constraint series_auto_publish_platforms_check check (auto_publish_platforms <@ array['youtube']::text[]);
--   alter table public.content_publication_jobs drop constraint content_publication_jobs_platform_allowed,
--     add constraint content_publication_jobs_platform_check check (platform = 'youtube');

do $$
declare
  target record;
  old_constraint record;
begin
  for target in
    select * from (values
      ('public.series'::regclass, 'auto_publish_platforms', 'series_auto_publish_platforms_allowed',
       'check (auto_publish_platforms <@ array[''youtube'', ''tiktok'']::text[])'),
      ('public.content_publication_jobs'::regclass, 'platform', 'content_publication_jobs_platform_allowed',
       'check (platform in (''youtube'', ''tiktok''))')
    ) as t(rel, col, new_name, new_def)
  loop
    if exists (select 1 from pg_constraint where conrelid = target.rel and conname = target.new_name) then
      continue;
    end if;

    -- Only single-column CHECK constraints on this exact column are replaced.
    for old_constraint in
      select c.conname
      from pg_constraint c
      join pg_attribute a on a.attrelid = c.conrelid and a.attnum = c.conkey[1]
      where c.conrelid = target.rel
        and c.contype = 'c'
        and array_length(c.conkey, 1) = 1
        and a.attname = target.col
    loop
      execute format('alter table %s drop constraint %I', target.rel, old_constraint.conname);
    end loop;

    execute format('alter table %s add constraint %I %s', target.rel, target.new_name, target.new_def);
  end loop;
end;
$$;
