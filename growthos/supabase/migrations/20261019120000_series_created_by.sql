-- Auteur d'une série (`series.created_by`), utilisé par le worker pour réserver l'Explainer aux administrateurs
-- (growthos/engine/explainer/access.py) : les épisodes sont mis en file par `queue_due_series_episodes`, qui ne
-- renseigne pas `requested_by`.
--
-- Non falsifiable depuis le client : à l'insertion, la valeur est forcée à auth.uid() ; une mise à jour cliente ne
-- peut pas la changer. service_role, postgres et les fonctions SECURITY DEFINER ne sont pas touchés. Les séries
-- existantes gardent NULL (inconnu) : l'Explainer leur est refusé, ce qui est le comportement voulu (aucune ne l'utilise).
alter table public.series
  add column if not exists created_by uuid references auth.users (id) on delete set null;

create or replace function public.guard_series_created_by()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if current_user not in ('authenticated', 'anon') then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.created_by := auth.uid();
  elsif new.created_by is distinct from old.created_by then
    new.created_by := old.created_by;
  end if;
  return new;
end;
$$;

revoke all on function public.guard_series_created_by() from public;

drop trigger if exists a0_guard_series_created_by on public.series;
create trigger a0_guard_series_created_by
  before insert or update on public.series
  for each row execute function public.guard_series_created_by();
