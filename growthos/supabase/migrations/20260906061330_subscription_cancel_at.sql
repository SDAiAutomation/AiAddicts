-- Résiliation d'abonnement depuis l'app (Réglages > Facturation).
--
-- Stripe garde l'abonnement `active` jusqu'à la fin de la période payée quand
-- on pose `cancel_at_period_end` : `subscription_status` seul ne suffit donc
-- pas à savoir qu'une résiliation est programmée. On stocke la date de fin
-- effective ; null = aucune résiliation en attente.
--
-- Alimenté par le webhook Stripe (customer.subscription.updated/deleted) et,
-- pour un retour immédiat sans attendre le webhook, par l'action serveur
-- cancelSubscription / resumeSubscription (service_role).

alter table organizations add column subscription_cancel_at timestamptz;

comment on column organizations.subscription_cancel_at is
  'Fin effective de l''abonnement si une résiliation est programmée (cancel_at_period_end côté Stripe). Null = abonnement en cours sans résiliation prévue.';

-- Colonne de facturation : écriture réservée au service_role (webhook +
-- actions billing), jamais à `authenticated` — cohérent avec les autres
-- colonnes stripe_* (voir 20260904220000_stripe_billing.sql).
