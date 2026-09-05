-- Nom d'utilisateur TikTok du compte OAuth connecté. Affiché dans l'UI
-- (fiche compte, section Publication) pour lever l'ambiguïté sur QUEL compte
-- TikTok est réellement lié. Rempli au callback OAuth et rafraîchi à chaque
-- publication via creator_info (scope video.publish, pas besoin de user.info).
alter table account_oauth_tokens add column tiktok_username text;
