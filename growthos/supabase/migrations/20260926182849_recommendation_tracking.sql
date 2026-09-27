-- Additive: existing recommendations/scripts remain readable without a trace.
-- Access remains governed by the existing account-scoped RLS policies.
alter table public.recommendations
  add column if not exists experiment jsonb
  check (experiment is null or jsonb_typeof(experiment) = 'object');

alter table public.content_items
  add column if not exists recommendation_report jsonb
  check (recommendation_report is null or jsonb_typeof(recommendation_report) = 'object');

comment on column public.recommendations.experiment is
  'Versioned primary hypothesis and historical baseline. Copied into the signed script generation receipt; not a causal prediction.';
comment on column public.content_items.recommendation_report is
  'Derived application diagnostic and descriptive outcome, bound to a script fingerprint. Missing measurements are null, never zero.';

-- updated_at previously changed only on worker heartbeats. A script edit must
-- invalidate classification/reports and advance the existing script version
-- for manual content as well as series, including edits after publication.
-- The existing series trigger runs first and may already advance the version.
create or replace function public.invalidate_recommendation_on_script_change()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if old.script is distinct from new.script then
    new.updated_at := clock_timestamp();
    new.recommendation_report := null;
    new.story_features := null;
    if new.script_version = old.script_version then
      new.script_version := old.script_version + 1;
    end if;
  end if;
  return new;
end;
$$;

revoke all on function public.invalidate_recommendation_on_script_change() from public, anon, authenticated;

create trigger track_recommendation_before_script_update
before update of script on public.content_items
for each row execute function public.invalidate_recommendation_on_script_change();
