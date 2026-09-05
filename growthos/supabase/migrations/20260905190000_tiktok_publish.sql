-- Un seul token OAuth actif par compte : la reconnexion doit remplacer
-- l'ancien enregistrement (upsert), pas en créer un second.
drop index if exists account_oauth_tokens_account_id_idx;
alter table account_oauth_tokens
  add constraint account_oauth_tokens_account_id_key unique (account_id);

-- Identifiant de suivi TikTok (Content Posting API), utile pour le support /
-- debug en cas de vidéo rejetée côté TikTok après publication.
alter table content_items add column tiktok_publish_id text;
