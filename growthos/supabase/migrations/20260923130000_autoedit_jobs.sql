-- AutoEdit (montage automatique de clips) — INFRASTRUCTURE uniquement, voir
-- AUTOEDIT_CONTRACT.md. Capacité EXPÉRIMENTALE : le worker ne traite ces jobs
-- que si AUTOEDIT_ENABLED=true (désactivé par défaut) et, tant qu'aucune
-- analyse vidéo réelle n'est branchée, le résultat est simulé et le
-- signale (quality.flags + manualReview).
--
-- Même patron que content_items : le frontend/l'app web insère la ligne
-- (pas de serveur HTTP Python), le worker la réclame de façon atomique.
-- Le fichier source est déposé directement par le navigateur dans un bucket
-- privé (chemin `<organization_id>/<job_id>/source`, calculé, jamais stocké).
--
-- Cycle côté client (droits volontairement minimaux, au niveau des colonnes) :
--   1. INSERT (status = 'uploading' par défaut) ;
--   2. upload du fichier vers autoedit-sources ;
--   3. UPDATE status = 'queued' — seule transition permise à l'utilisateur.
-- Tout le reste (progress, événements, plan, résultat, erreur, crédits) est
-- écrit par service_role uniquement.

create table public.autoedit_jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  created_by uuid references public.profiles(id) on delete set null default auth.uid(),
  profile text not null default 'sports' check (profile in ('sports')),

  status text not null default 'uploading' check (status in (
    'queued', 'uploading', 'analyzing', 'planning', 'rendering', 'review', 'completed', 'failed'
  )),
  -- 0..100, NULL si inconnu. Jamais déduit du statut côté frontend.
  progress integer check (progress between 0 and 100),
  -- Texte affiché tel quel à l'utilisateur (posé par le backend, voir
  -- engine/autoedit.py STAGE_LABELS).
  stage_label text,

  input_filename text not null check (char_length(input_filename) between 1 and 255),
  input_duration_seconds numeric check (input_duration_seconds is null or input_duration_seconds > 0),

  focus text not null check (focus in ('best', 'player', 'goals')),
  player_number text check (player_number is null or char_length(player_number) <= 8),
  style text not null check (style in ('hype', 'cinematic', 'clean', 'emotional')),
  duration_seconds integer not null check (duration_seconds in (15, 30, 60)),

  -- { code, message, retryable } — `code` est localisable côté frontend.
  error jsonb,
  -- Événements détectés (AutoEditEvent[]), persistés pour être réutilisés.
  events jsonb,
  -- AutoEditPlan (EDL validée avant rendu).
  plan jsonb,
  -- { score, flags, manualReview }
  quality jsonb,
  -- { analysisCost, renderCost, currency } — tarifs jamais devinés : null.
  usage jsonb,
  video_url text,
  poster_url text,

  -- Observabilité interne : analyseur utilisé, simulé ou non, durée par étape.
  run_report jsonb,
  -- Nombre de réclamations par un worker ; borne les reprises après crash.
  attempts integer not null default 0,
  -- Crédits demandés pour ce job (0 = analyse simulée ; Business : demandé mais jamais débité).
  credits_reserved integer not null default 0 check (credits_reserved >= 0),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index autoedit_jobs_org_created_idx on public.autoedit_jobs (organization_id, created_at desc);
-- File du worker : jobs 'queued' du plus ancien au plus récent.
create index autoedit_jobs_queue_idx on public.autoedit_jobs (created_at) where status = 'queued';
create index autoedit_jobs_created_by_idx on public.autoedit_jobs (created_by);

-- Contrairement au reste du schéma, un trigger tient updated_at : la seule
-- écriture du client (uploading -> queued) doit être visible au polling.
create or replace function internal.touch_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
revoke execute on function internal.touch_updated_at() from public, anon, authenticated;

create trigger autoedit_jobs_touch_updated_at
  before update on public.autoedit_jobs
  for each row execute function internal.touch_updated_at();

alter table public.autoedit_jobs enable row level security;

create policy "autoedit_jobs_member_select" on public.autoedit_jobs for select
  using (organization_id in (select internal.current_user_org_ids()));
create policy "autoedit_jobs_insert_roles" on public.autoedit_jobs for insert
  with check (internal.has_org_role(organization_id, array['owner', 'strategist', 'editor']));
-- L'utilisateur ne peut faire avancer que sa propre file d'upload.
create policy "autoedit_jobs_confirm_upload" on public.autoedit_jobs for update
  using (status = 'uploading' and internal.has_org_role(organization_id, array['owner', 'strategist', 'editor']))
  with check (status in ('uploading', 'queued'));

-- Droits au niveau des colonnes (défense en profondeur avec les policies) :
-- un membre ne peut ni fixer un statut, ni un crédit, ni un résultat.
revoke all on public.autoedit_jobs from anon, authenticated;
grant select on public.autoedit_jobs to authenticated;
grant insert (organization_id, profile, input_filename, input_duration_seconds, focus, player_number, style, duration_seconds)
  on public.autoedit_jobs to authenticated;
grant update (status) on public.autoedit_jobs to authenticated;

comment on table public.autoedit_jobs is
  'Jobs AutoEdit (expérimental). Voir AUTOEDIT_CONTRACT.md. Source vidéo : bucket autoedit-sources, chemin <organization_id>/<id>/source.';
comment on column public.autoedit_jobs.credits_reserved is
  'Crédits demandés à la réservation (quota commun avec Generate, consommation propre à AutoEdit). 0 pour une analyse simulée ; rien n''est réellement débité pour Business.';
comment on column public.autoedit_jobs.usage is
  'Coûts { analysisCost, renderCost, currency }. null = non mesuré, jamais deviné.';

-- Bucket privé pour les vidéos sources. La limite de taille du bucket est
-- aussi bornée par la limite globale du projet Supabase (Storage settings).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('autoedit-sources', 'autoedit-sources', false, 524288000,
        array['video/mp4', 'video/quicktime', 'video/webm'])
on conflict (id) do nothing;

-- Dépôt autorisé uniquement vers le dossier d'un job de son organisation
-- encore en 'uploading'. Lecture : service_role seulement (worker) — aucune
-- policy SELECT, donc jamais d'accès direct à la source d'un autre utilisateur.
create policy "autoedit_sources_upload" on storage.objects for insert to authenticated
  with check (
    bucket_id = 'autoedit-sources'
    and exists (
      select 1 from public.autoedit_jobs j
      where j.status = 'uploading'
        and j.organization_id::text = (storage.foldername(name))[1]
        and j.id::text = (storage.foldername(name))[2]
        and (storage.foldername(name))[3] is null
        and storage.filename(name) = 'source'
        and internal.has_org_role(j.organization_id, array['owner', 'strategist', 'editor'])
    )
  );

-- --- Crédits : quota commun avec Generate, consommation distincte -----------
-- Même modèle que reserve/refund_generation_credit (crédits mensuels d'abord,
-- puis pack ; lignes de ledger séparées pour recréditer la bonne réserve), mais
-- le montant est variable (durée analysée / rendu / variantes) et la référence
-- est le job AutoEdit : `related_autoedit_job_id`, raisons `autoedit_*`.

alter table public.credits_ledger
  add column if not exists related_autoedit_job_id uuid references public.autoedit_jobs(id) on delete set null;
create index if not exists credits_ledger_autoedit_job_idx
  on public.credits_ledger (related_autoedit_job_id) where related_autoedit_job_id is not null;

create or replace function public.reserve_autoedit_credit(p_job_id uuid, p_credits integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_org_id uuid;
  v_plan text;
  v_balance integer;
  v_pack integer;
  v_net integer;
  v_from_pack integer;
  v_from_monthly integer;
begin
  if p_credits is null or p_credits <= 0 then return false; end if;

  select organization_id into v_org_id from autoedit_jobs where id = p_job_id;
  if v_org_id is null then return false; end if;

  select plan, credits_balance, pack_credits into v_plan, v_balance, v_pack
  from organizations where id = v_org_id for update;

  if v_plan = 'business' then return true; end if;

  -- Idempotent : une reprise après crash retrouve sa réservation.
  select coalesce(sum(delta), 0) into v_net
  from credits_ledger
  where related_autoedit_job_id = p_job_id
    and reason in ('autoedit_reserved', 'autoedit_refund', 'autoedit_reserved_pack', 'autoedit_refund_pack');
  if v_net < 0 then return true; end if;

  if v_balance < p_credits then return false; end if;

  -- Crédits mensuels restants = solde - pack ; consommés en premier.
  v_from_monthly := least(p_credits, greatest(v_balance - v_pack, 0));
  v_from_pack := p_credits - v_from_monthly;

  update organizations
  set credits_balance = credits_balance - p_credits,
      pack_credits = pack_credits - v_from_pack
  where id = v_org_id;

  if v_from_monthly > 0 then
    insert into credits_ledger (organization_id, delta, reason, related_autoedit_job_id, balance_after)
    values (v_org_id, -v_from_monthly, 'autoedit_reserved', p_job_id, v_balance - v_from_monthly);
  end if;
  if v_from_pack > 0 then
    insert into credits_ledger (organization_id, delta, reason, related_autoedit_job_id, balance_after)
    values (v_org_id, -v_from_pack, 'autoedit_reserved_pack', p_job_id, v_balance - p_credits);
  end if;
  return true;
end;
$$;

create or replace function public.refund_autoedit_credit(p_job_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_org_id uuid;
  v_plan text;
  v_balance integer;
  v_net_monthly integer;
  v_net_pack integer;
  v_monthly integer;
  v_pack integer;
begin
  select organization_id into v_org_id from autoedit_jobs where id = p_job_id;
  if v_org_id is null then return false; end if;

  select plan, credits_balance into v_plan, v_balance
  from organizations where id = v_org_id for update;
  if v_plan = 'business' then return false; end if;

  select coalesce(sum(delta), 0) into v_net_monthly
  from credits_ledger
  where related_autoedit_job_id = p_job_id and reason in ('autoedit_reserved', 'autoedit_refund');
  select coalesce(sum(delta), 0) into v_net_pack
  from credits_ledger
  where related_autoedit_job_id = p_job_id and reason in ('autoedit_reserved_pack', 'autoedit_refund_pack');

  v_monthly := greatest(-v_net_monthly, 0);
  v_pack := greatest(-v_net_pack, 0);
  if v_monthly + v_pack = 0 then return false; end if;

  update organizations
  set credits_balance = credits_balance + v_monthly + v_pack,
      pack_credits = pack_credits + v_pack
  where id = v_org_id;

  if v_monthly > 0 then
    insert into credits_ledger (organization_id, delta, reason, related_autoedit_job_id, balance_after)
    values (v_org_id, v_monthly, 'autoedit_refund', p_job_id, v_balance + v_monthly);
  end if;
  if v_pack > 0 then
    insert into credits_ledger (organization_id, delta, reason, related_autoedit_job_id, balance_after)
    values (v_org_id, v_pack, 'autoedit_refund_pack', p_job_id, v_balance + v_monthly + v_pack);
  end if;
  return true;
end;
$$;

revoke all on function public.reserve_autoedit_credit(uuid, integer) from public, anon, authenticated;
revoke all on function public.refund_autoedit_credit(uuid) from public, anon, authenticated;
grant execute on function public.reserve_autoedit_credit(uuid, integer) to service_role;
grant execute on function public.refund_autoedit_credit(uuid) to service_role;
