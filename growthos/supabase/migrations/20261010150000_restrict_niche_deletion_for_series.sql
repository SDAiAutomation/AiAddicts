-- A series must retain its editorial niche. Deleting an in-use niche should
-- fail instead of silently changing series.niche_id to null.
alter table public.series
  drop constraint if exists series_niche_id_fkey;

alter table public.series
  add constraint series_niche_id_fkey
  foreign key (niche_id) references public.niches(id) on delete restrict;
