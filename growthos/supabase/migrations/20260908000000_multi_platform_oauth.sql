-- Multi-plateforme : un compte peut désormais connecter plusieurs
-- plateformes en même temps (TikTok + YouTube, + futur), au lieu d'un seul
-- token OAuth par compte. accounts.platform reste un tag "plateforme
-- principale" (affichage, niche par défaut) mais ne conditionne plus quelles
-- plateformes on peut connecter/publier sur ce compte — voir le commentaire
-- de 20260906190734_youtube_publish.sql, qui documentait l'ancienne
-- hypothèse "un compte = une plateforme = un token".

alter table account_oauth_tokens drop constraint account_oauth_tokens_account_id_key;

alter table account_oauth_tokens add column platform text;

-- Backfill : la ligne existante garde la plateforme de son compte.
update account_oauth_tokens t
set platform = a.platform
from accounts a
where a.id = t.account_id;

alter table account_oauth_tokens alter column platform set not null;

alter table account_oauth_tokens add constraint account_oauth_tokens_platform_check
  check (platform = any (array['tiktok'::text, 'instagram'::text, 'youtube'::text]));

alter table account_oauth_tokens add constraint account_oauth_tokens_account_id_platform_key
  unique (account_id, platform);

comment on column account_oauth_tokens.platform is
  'Plateforme de cette connexion OAuth. Un compte peut avoir une ligne par plateforme (tiktok, youtube, instagram plus tard) — clé (account_id, platform).';
