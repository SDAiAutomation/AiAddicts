-- Publication YouTube (Shorts) — même modèle que TikTok. Un compte Faceloop
-- avec platform='youtube' relie une chaîne YouTube via OAuth Google
-- (scope youtube.upload) ; le token vit dans account_oauth_tokens
-- (UNIQUE(account_id), un compte = une plateforme = un token).

alter table account_oauth_tokens add column youtube_channel_id text;
alter table account_oauth_tokens add column youtube_channel_title text;

comment on column account_oauth_tokens.youtube_channel_title is
  'Nom de la chaîne YouTube liée, affiché sur la fiche compte.';

-- Identifiant de la vidéo YouTube après publication (suivi / lien).
alter table content_items add column youtube_video_id text;
