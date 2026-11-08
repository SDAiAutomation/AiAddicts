-- Instagram Reels (Meta) : connexion par fiche compte + suivi des publications.
-- ADDITIVE, A RELIRE, NE PAS APPLIQUER EN PRODUCTION SANS DECISION HUMAINE.
--
-- 1. Les connexions restent dans account_oauth_tokens (une ligne par compte et
--    plateforme, 'instagram' est deja autorise). Colonnes nullables : TikTok et
--    YouTube ne changent pas.
-- 2. social_publications garde une ligne par tentative. L'index partiel unique
--    interdit deux publications actives ou reussies du meme contenu vers la
--    meme cible : c'est lui qui rend le double clic inoffensif.
-- 3. Le role authenticated ne lit que des colonnes sans secret et n'ecrit rien :
--    les ecritures passent par le serveur, apres controle de l'organisation.

alter table public.account_oauth_tokens
  add column if not exists external_account_id text,
  add column if not exists external_username text,
  add column if not exists external_account_type text,
  add column if not exists external_business_id text,
  add column if not exists external_page_id text,
  add column if not exists granted_scopes text[],
  add column if not exists auth_flow text,
  add column if not exists connected_by uuid references auth.users(id) on delete set null,
  add column if not exists updated_at timestamptz not null default now();

alter table public.account_oauth_tokens
  drop constraint if exists account_oauth_tokens_status_check;
alter table public.account_oauth_tokens
  add constraint account_oauth_tokens_status_check
  check (status in ('connected', 'expired', 'revoked', 'error', 'insufficient_scope'));

alter table public.account_oauth_tokens
  drop constraint if exists account_oauth_tokens_auth_flow_check;
alter table public.account_oauth_tokens
  add constraint account_oauth_tokens_auth_flow_check
  check (auth_flow is null or auth_flow in ('unified', 'facebook_login'));

comment on column public.account_oauth_tokens.auth_flow is
  'Flux Meta qui a produit le jeton. Ne jamais melanger les scopes de deux flux.';

-- Les jetons chiffres restent hors de portee de authenticated (20260919152000).
grant select (
  external_account_id, external_username, external_account_type,
  granted_scopes, auth_flow, updated_at
) on table public.account_oauth_tokens to authenticated;

create table if not exists public.social_publications (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  account_id uuid not null references public.accounts(id) on delete cascade,
  content_item_id uuid not null references public.content_items(id) on delete cascade,
  platform text not null check (platform in ('instagram', 'facebook')),
  target_external_id text not null check (length(target_external_id) between 1 and 64),
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'publishing', 'published', 'failed')),
  caption text check (caption is null or char_length(caption) <= 2200),
  container_id text,
  external_media_id text,
  permalink text check (permalink is null or permalink like 'https://%'),
  error_code text,
  publish_attempts integer not null default 0 check (publish_attempts between 0 and 10),
  poll_count integer not null default 0 check (poll_count >= 0),
  poll_errors integer not null default 0 check (poll_errors >= 0),
  poll_deadline timestamptz,
  next_poll_at timestamptz,
  requested_by uuid references auth.users(id) on delete set null,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists social_publications_one_active_per_target
  on public.social_publications (content_item_id, platform, target_external_id)
  where status in ('pending', 'processing', 'publishing', 'published');

create index if not exists social_publications_item_recent
  on public.social_publications (content_item_id, platform, created_at desc);
create index if not exists social_publications_account_idx
  on public.social_publications (account_id);
create index if not exists social_publications_organization_idx
  on public.social_publications (organization_id);
create index if not exists social_publications_requested_by_idx
  on public.social_publications (requested_by);

alter table public.social_publications enable row level security;

revoke all on table public.social_publications from anon, authenticated;
grant select (
  id, organization_id, account_id, content_item_id, platform, target_external_id, status,
  caption, external_media_id, permalink, error_code, poll_deadline, published_at, created_at, updated_at
) on table public.social_publications to authenticated;

drop policy if exists "social_publications_member_select" on public.social_publications;
create policy "social_publications_member_select" on public.social_publications
  for select to authenticated
  using (organization_id in (select internal.current_user_org_ids()));

comment on table public.social_publications is
  'Une ligne par tentative de publication sociale. Ecriture serveur uniquement. Ne contient ni jeton ni URL signee.';
