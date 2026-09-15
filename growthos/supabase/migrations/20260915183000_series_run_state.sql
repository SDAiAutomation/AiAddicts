-- Réservation atomique des épisodes de série.
-- Deux appels cron peuvent lire la même série comme due. Cette fonction
-- avance le planning et réserve le numéro d'épisode dans une seule UPDATE,
-- uniquement si le créneau lu par l'appelant est toujours courant.

alter table public.series
  add column if not exists last_run_at timestamptz,
  add column if not exists last_error text,
  add column if not exists last_content_item_id uuid references public.content_items(id) on delete set null;

create unique index if not exists content_items_series_episode_unique
  on public.content_items(series_id, episode_number)
  where series_id is not null and episode_number is not null;

create or replace function public.claim_series_run(
  p_series_id uuid,
  p_expected_next_run_at timestamptz,
  p_next_run_at timestamptz
)
returns integer
language sql
security definer
set search_path = public
as $$
  update public.series
  set next_run_at = p_next_run_at,
      last_run_at = now(),
      last_error = null
  where id = p_series_id
    and status = 'active'
    and next_run_at = p_expected_next_run_at
    and next_run_at <= now()
  returning episode_count + 1;
$$;

revoke all on function public.claim_series_run(uuid, timestamptz, timestamptz) from public;
grant execute on function public.claim_series_run(uuid, timestamptz, timestamptz) to service_role;

comment on function public.claim_series_run(uuid, timestamptz, timestamptz) is
  'Réserve atomiquement le prochain numéro d épisode et avance le planning. Retourne null si le créneau a déjà été réclamé.';
