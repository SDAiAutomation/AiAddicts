-- TikTok Direct Post : représenter l'état réel de la publication.
--
-- Avant : tiktok_publish_id renseigné = « publié » (le statut passait à published
-- dès que le téléversement était accepté, sans confirmation de TikTok).
-- Maintenant : l'état suit publish/status/fetch (PROCESSING_UPLOAD ->
-- PUBLISH_COMPLETE ou FAILED).
--
-- Additive et rétro-compatible : colonnes nullables, aucune ligne existante
-- modifiée. Une ligne avec tiktok_publish_id et SANS tiktok_publish_status est
-- une publication antérieure à cette migration : elle reste traitée comme publiée
-- (jamais en cours ni en échec). NULL = « pas de suivi TikTok », pas « échec ».

alter table content_items
  add column if not exists tiktok_publish_status text,
  add column if not exists tiktok_publish_error text;

alter table content_items
  drop constraint if exists content_items_tiktok_publish_status_check;
alter table content_items
  add constraint content_items_tiktok_publish_status_check
  check (
    tiktok_publish_status is null
    or tiktok_publish_status in (
      'PROCESSING_UPLOAD', 'PROCESSING_DOWNLOAD', 'SEND_TO_USER_INBOX', 'PUBLISH_COMPLETE', 'FAILED'
    )
  );

comment on column content_items.tiktok_publish_status is
  'Statut TikTok publish/status/fetch (valeurs de l''API). NULL = publication antérieure au suivi ou jamais publié.';
comment on column content_items.tiktok_publish_error is
  'fail_reason TikTok (ou faceloop_upload_failed) quand tiktok_publish_status = FAILED. Usage diagnostic, jamais affiché tel quel.';
