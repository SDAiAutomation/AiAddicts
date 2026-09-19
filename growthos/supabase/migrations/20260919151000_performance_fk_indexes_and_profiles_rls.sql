-- Index sur les clés étrangères non couvertes (jointures et suppressions en cascade).
create index if not exists content_items_requested_by_idx on public.content_items(requested_by);
create index if not exists credits_ledger_related_content_item_id_idx on public.credits_ledger(related_content_item_id);
create index if not exists series_last_content_item_id_idx on public.series(last_content_item_id);
create index if not exists series_niche_id_idx on public.series(niche_id);

-- auth.uid() enveloppé dans un select : évalué une fois par requête (initplan)
-- au lieu d'une fois par ligne. Même logique, mêmes rôles, sans interruption.
alter policy profiles_self_select on public.profiles using (id = (select auth.uid()));
alter policy profiles_self_update on public.profiles using (id = (select auth.uid()));
alter policy profiles_self_insert on public.profiles with check (id = (select auth.uid()));
