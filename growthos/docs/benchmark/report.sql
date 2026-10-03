-- Rapport du benchmark (lot L5). Éditeur SQL / service_role uniquement.
-- Les vidéos du benchmark sont repérées par le préfixe [BENCH-nn] du titre.
-- Lecture seule : aucune écriture.

-- 1. Une ligne par vidéo : réussite, statut, coût, délai, drapeaux qualité.
select
  substring(ci.title from '\[(BENCH-\d+)\]') as bench_id,
  ci.status,
  ci.quality_score,
  ci.quality_flags,
  (ci.generation_cost_report->>'totalEstimatedCost')::numeric as cost_usd,
  e_done.created_at - e_start.created_at as render_duration,
  ci.error
from public.content_items ci
left join lateral (
  select created_at from public.product_events
  where content_item_id = ci.id and event = 'generation_started'
  order by created_at limit 1
) e_start on true
left join lateral (
  select created_at from public.product_events
  where content_item_id = ci.id and event = 'generation_completed'
  order by created_at limit 1
) e_done on true
where ci.title like '[BENCH-%'
order by bench_id;

-- 2. Synthèse : taux de réussite, coût médian et P90, délai médian.
select
  count(*) as videos,
  count(*) filter (where status in ('video', 'quality_check', 'published')) as rendered,
  count(*) filter (where status = 'quality_check') as quality_check,
  count(*) filter (where status = 'failed') as failed,
  round(avg((generation_cost_report->>'totalEstimatedCost')::numeric), 4) as avg_cost_usd,
  round((percentile_cont(0.5) within group (order by (generation_cost_report->>'totalEstimatedCost')::numeric))::numeric, 4) as median_cost_usd,
  round((percentile_cont(0.9) within group (order by (generation_cost_report->>'totalEstimatedCost')::numeric))::numeric, 4) as p90_cost_usd,
  round(sum((generation_cost_report->>'totalEstimatedCost')::numeric), 2) as total_cost_usd
from public.content_items
where title like '[BENCH-%';

-- 3. Tous les essais (y compris corrections) : un run = une ligne generation_completed.
select
  substring(ci.title from '\[(BENCH-\d+)\]') as bench_id,
  e.created_at,
  (e.props->>'cost_usd')::numeric as run_cost_usd,
  (e.props->>'duration_s')::numeric as run_seconds,
  e.props->'assets_reused' as assets_reused
from public.product_events e
join public.content_items ci on ci.id = e.content_item_id
where e.event = 'generation_completed' and ci.title like '[BENCH-%'
order by bench_id, e.created_at;

-- 4. Échecs enregistrés pendant le benchmark.
select substring(ci.title from '\[(BENCH-\d+)\]') as bench_id, e.created_at, e.props->>'error' as error
from public.product_events e
join public.content_items ci on ci.id = e.content_item_id
where e.event = 'generation_failed' and ci.title like '[BENCH-%'
order by e.created_at;

-- 5. Coût par vidéo satisfaisante, restreint au benchmark.
select
  count(*) as satisfying_videos,
  round(avg(vs.total_cost_usd), 4) as avg_cost_usd,
  round((percentile_cont(0.5) within group (order by vs.total_cost_usd))::numeric, 4) as median_cost_usd,
  round((percentile_cont(0.9) within group (order by vs.total_cost_usd))::numeric, 4) as p90_cost_usd
from public.video_satisfaction vs
join public.content_items ci on ci.id = vs.content_item_id
where ci.title like '[BENCH-%' and vs.satisfied_at is not null;
