-- Lot L4 : les tables de mémoire de série avaient hérité de TRUNCATE,
-- REFERENCES et TRIGGER pour `authenticated` (privilèges par défaut). Seuls
-- SELECT / INSERT / UPDATE / DELETE sont nécessaires, filtrés par RLS.
-- Idempotent.
revoke all on table public.series_characters, public.series_canon_facts from authenticated;
grant select, insert, update, delete on table public.series_characters, public.series_canon_facts to authenticated;
