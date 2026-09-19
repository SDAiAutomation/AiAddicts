-- Les pages ont seulement besoin de l'état de connexion et des noms de chaîne.
-- Les jetons chiffrés restent accessibles au service_role, après les contrôles
-- d'organisation effectués par les Server Actions et callbacks.
revoke all on table public.account_oauth_tokens from anon, authenticated;

grant select (
  id,
  account_id,
  platform,
  expires_at,
  status,
  last_checked_at,
  created_at,
  tiktok_username,
  youtube_channel_id,
  youtube_channel_title
) on table public.account_oauth_tokens to authenticated;
