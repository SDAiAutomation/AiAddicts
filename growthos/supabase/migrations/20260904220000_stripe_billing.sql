-- Facturation Stripe : aligne organizations.plan sur les 3 offres réelles
-- (starter/pro/business — l'ancien starter/growth/agency/agency_pro ne
-- correspondait à rien d'affiché) et ajoute le nécessaire pour relier une
-- organisation à son abonnement Stripe.

alter table organizations drop constraint organizations_plan_check;
alter table organizations add constraint organizations_plan_check
  check (plan in ('starter', 'pro', 'business'));

alter table organizations add column stripe_customer_id text unique;
alter table organizations add column stripe_subscription_id text unique;
alter table organizations add column stripe_price_id text;
alter table organizations add column subscription_status text
  check (subscription_status is null or subscription_status in (
    'trialing', 'active', 'past_due', 'canceled', 'unpaid', 'incomplete', 'incomplete_expired', 'paused'
  ));

comment on column organizations.stripe_customer_id is
  'Client Stripe associé (créé au premier passage en Checkout). Une organisation = un client Stripe.';
comment on column organizations.stripe_subscription_id is
  'Abonnement Stripe actif, mis à jour par le webhook (api/webhooks/stripe). Null si jamais souscrit ou résilié.';
comment on column organizations.stripe_price_id is
  'Price Stripe couramment souscrit — distingue le plan ET la cadence (mensuel/annuel), voir lib/stripe-plans.ts côté growthos-web.';
comment on column organizations.subscription_status is
  'Reflet du statut Stripe (subscription.status). Null = jamais souscrit (plan starter par défaut, hors Stripe).';

-- Lecture déjà couverte par la policy existante organizations_member_select
-- (member de l'org). Écriture : uniquement le webhook (service_role, RLS
-- non applicable).
--
-- Durcissement au passage : la policy "organizations_owner_update" existante
-- autorise un owner à UPDATE sa ligne organizations sans restriction de
-- colonne (RLS ne gate que les LIGNES, pas les colonnes) — un owner pouvait
-- donc déjà, en frappant l'API REST Supabase directement (hors app), se
-- passer en plan/statut d'abonnement de son choix. Restreint via des GRANT
-- au niveau colonne : authenticated ne peut modifier que `name`, jamais
-- `plan`/`stripe_*`/`subscription_status`/`credits_balance` (ces colonnes ne
-- doivent bouger que via le webhook Stripe en service_role, qui contourne
-- les grants comme les policies RLS).
revoke update on organizations from authenticated;
grant update (name) on organizations to authenticated;
