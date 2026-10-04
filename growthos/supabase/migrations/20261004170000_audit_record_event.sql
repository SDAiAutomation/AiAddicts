-- Audit niveau 1 : point d'écriture unique vers audit.events.
--
-- Constat (2026-10-04) : audit.events existe depuis le début mais compte 0 ligne,
-- et le rôle service_role n'a NI usage sur le schéma `audit` NI droit INSERT sur la
-- table (le commentaire du schéma supposait qu'il « contourne » ces droits : il ne
-- contourne que la RLS). Plutôt que d'ouvrir le schéma à service_role, une fonction
-- SECURITY DEFINER dans `public` fait l'insertion, avec des garde-fous :
--   - action de la forme `domaine.evenement` (minuscules et underscore) ;
--   - result / risk_level validés avant l'insertion ;
--   - metadata : objet JSON borné (4 Ko), sans clé qui ressemble à un secret ;
--   - exécutable par service_role uniquement.
-- La table reste en ajout seul (déclencheurs audit.forbid_mutation inchangés).

create or replace function public.record_audit_event(
  p_actor_id uuid,
  p_tenant_id uuid,
  p_action text,
  p_resource_type text default null,
  p_resource_id uuid default null,
  p_result text default 'success',
  p_risk_level text default 'low',
  p_metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_metadata jsonb := coalesce(p_metadata, '{}'::jsonb);
begin
  if p_action is null or p_action !~ '^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$' then
    raise exception 'invalid_audit_action';
  end if;
  if p_result not in ('success', 'failure') then
    raise exception 'invalid_audit_result';
  end if;
  if p_risk_level not in ('low', 'medium', 'high') then
    raise exception 'invalid_audit_risk_level';
  end if;
  if jsonb_typeof(v_metadata) <> 'object' then
    raise exception 'invalid_audit_metadata';
  end if;
  if octet_length(v_metadata::text) > 4000 then
    raise exception 'audit_metadata_too_large';
  end if;
  if exists (
    select 1 from jsonb_object_keys(v_metadata) as k
    where k ~* '(token|secret|password|passwd|api_?key|authorization|cookie)'
  ) then
    raise exception 'secret_in_audit_metadata';
  end if;

  insert into audit.events
    (actor_id, tenant_id, action, resource_type, resource_id, result, risk_level, metadata)
  values
    (p_actor_id, p_tenant_id, p_action, p_resource_type, p_resource_id, p_result, p_risk_level, v_metadata);
end;
$$;

revoke all on function public.record_audit_event(uuid, uuid, text, text, uuid, text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.record_audit_event(uuid, uuid, text, text, uuid, text, text, jsonb)
  to service_role;

comment on function public.record_audit_event(uuid, uuid, text, text, uuid, text, text, jsonb) is
  'Écrit une ligne dans audit.events (ajout seul). service_role uniquement. Jamais de jeton, mot de passe ou clé dans p_metadata.';
