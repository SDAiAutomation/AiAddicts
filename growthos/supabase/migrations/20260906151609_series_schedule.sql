-- Planning des séries : passe d'un simple intervalle (`cadence_hours`) à un
-- modèle de créneaux — l'utilisateur choisit les jours actifs et l'heure (ou
-- les heures) de la journée, dans son fuseau. Ça permet d'afficher une vraie
-- date/heure ("mercredi 9 oct. à 09:00") au lieu d'un "dans 14h" flottant, et
-- de ne plus voir les épisodes dériver vers l'heure où le cron passe.
--
-- `cadence_hours` est conservé (colonne, défaut) pour ne rien casser mais
-- n'est plus lu par le code.

alter table series
  add column run_times text[] not null default array['09:00'],
  add column run_days integer[] not null default array[0, 1, 2, 3, 4, 5, 6],
  add column timezone text not null default 'Europe/Paris';

comment on column series.run_times is
  'Heures de génération dans la journée, format "HH:MM" (fuseau = series.timezone). Ex: {"09:00","18:00"}.';
comment on column series.run_days is
  'Jours actifs, 0 = dimanche .. 6 = samedi.';
comment on column series.timezone is
  'Fuseau IANA (ex: Europe/Paris) dans lequel run_times est interprété et affiché.';

-- Créneau existant : garde un défaut sûr (9h tous les jours). Les séries
-- déjà créées repartent sur ce planning, ajustable dans le formulaire.
update series set run_times = array['09:00'], run_days = array[0, 1, 2, 3, 4, 5, 6]
where run_times is null or run_days is null;
