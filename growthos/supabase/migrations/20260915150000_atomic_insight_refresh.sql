-- Remplace en une transaction la mémoire dérivée d'un compte. Les snapshots
-- content_performance restent la source de vérité ; insights est reconstruite
-- après chaque nouveau relevé par engine.learning.

alter table insights add column metadata jsonb not null default '{}';

create or replace function public.replace_account_insights(
  p_account_id uuid,
  p_insights jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from insights where account_id = p_account_id;

  insert into insights (account_id, kind, label, performance_score, sample_size, metadata)
  select
    p_account_id,
    item.kind,
    item.label,
    item.performance_score,
    item.sample_size,
    item.metadata
  from jsonb_to_recordset(coalesce(p_insights, '[]'::jsonb)) as item(
    kind text,
    label text,
    performance_score numeric,
    sample_size integer,
    metadata jsonb
  );
end;
$$;

revoke all on function public.replace_account_insights(uuid, jsonb)
from public, anon, authenticated;
grant execute on function public.replace_account_insights(uuid, jsonb) to service_role;
