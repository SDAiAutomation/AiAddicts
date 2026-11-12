-- Directives éditoriales d'une série (Series Intelligence, growthos-web PR #214-#218).
--
-- Migration déjà appliquée à la base par le propriétaire ; ce fichier aligne le dépôt du moteur sur le schéma.
-- Colonne facultative : NULL = comportement automatique (la premise est relue à chaque épisode). Le site relit et
-- re-valide la valeur à chaque génération ; le moteur Python ne lit pas cette colonne.
-- Idempotente : peut être rejouée sans effet.

alter table public.series
  add column if not exists directives jsonb;

alter table public.series
  drop constraint if exists series_directives_shape;
alter table public.series
  add constraint series_directives_shape
  check (directives is null or (jsonb_typeof(directives) = 'object' and pg_column_size(directives) <= 2000));

-- Retour arrière :
--   alter table public.series drop constraint if exists series_directives_shape;
--   alter table public.series drop column if exists directives;
