-- Suivi de rentabilité : coût de génération agrégé (content_items.
-- generation_cost_report, écrit par le worker). À croiser avec le prix du plan
-- (Stripe) pour obtenir la marge. Lecture réservée à service_role / éditeur SQL :
-- ces vues ne doivent JAMAIS être exposées via l'API à anon/authenticated.

create or replace view public.generation_cost_by_org_month
with (security_invoker = true) as
select
  o.id as organization_id,
  o.name as organization_name,
  o.plan,
  date_trunc('month', ci.created_at)::date as month,
  count(*) as generations,
  round(sum((ci.generation_cost_report->>'totalEstimatedCost')::numeric), 4) as total_cost_usd,
  round(avg((ci.generation_cost_report->>'totalEstimatedCost')::numeric), 4) as avg_cost_usd,
  count(*) filter (where (ci.generation_cost_report->>'overBudget')::boolean) as over_budget
from public.content_items ci
join public.accounts a on a.id = ci.account_id
join public.organizations o on o.id = a.organization_id
where ci.generation_cost_report is not null
group by o.id, o.name, o.plan, date_trunc('month', ci.created_at);

create or replace view public.generation_cost_weekly
with (security_invoker = true) as
select
  date_trunc('week', created_at)::date as week,
  count(*) as generations,
  round(avg((generation_cost_report->>'totalEstimatedCost')::numeric), 4) as avg_cost_usd,
  round(sum((generation_cost_report->>'totalEstimatedCost')::numeric), 4) as total_cost_usd,
  round(avg((generation_cost_report->'images'->>'cost')::numeric), 4) as avg_images_usd,
  round(avg((generation_cost_report->'voice'->>'cost')::numeric), 4) as avg_voice_usd
from public.content_items
where generation_cost_report is not null
group by date_trunc('week', created_at)
order by week desc;

revoke all on public.generation_cost_by_org_month from public, anon, authenticated;
revoke all on public.generation_cost_weekly from public, anon, authenticated;
grant select on public.generation_cost_by_org_month to service_role;
grant select on public.generation_cost_weekly to service_role;
