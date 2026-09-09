-- Rognage (couper début/fin) de la vidéo finale, post-génération.
--
-- Orthogonal au `status` principal : la vidéo reste 'video' / 'quality_check'
-- / 'published' pendant qu'un job de rognage tourne. worker.py a un second
-- point d'entrée (repo.claim_trim_job) qui repart du MP4 déjà rendu et
-- stocké — ni ElevenLabs ni rendu des clips, juste un ffmpeg de découpe.
--
-- File du job : trim_status 'pending' (demandé par le front) -> 'processing'
-- (réclamé par un worker) -> NULL (fait, ou échec avec trim_error).

alter table content_items
  add column trim_start numeric not null default 0,
  add column trim_end numeric,
  add column trim_status text,
  add column trim_error text,
  add column original_video_url text;

alter table content_items
  add constraint content_items_trim_status_check
    check (trim_status is null or trim_status in ('pending', 'processing')),
  add constraint content_items_trim_bounds_check
    check (trim_start >= 0 and (trim_end is null or trim_end > trim_start));

comment on column content_items.trim_start is
  'Début conservé (s) dans la vidéo d''origine. 0 = depuis le début.';
comment on column content_items.trim_end is
  'Fin conservée (s) dans la vidéo d''origine. NULL = jusqu''à la fin.';
comment on column content_items.trim_status is
  'File du job de rognage : pending (demandé) -> processing (worker) -> NULL (fait). trim_error si le dernier run a échoué.';
comment on column content_items.original_video_url is
  'URL publique de la version non rognée (<id>.original.mp4), posée au 1er rognage. Sert au « rétablir la version complète » et à re-rogner depuis la source intacte. Remise à NULL par une régénération complète.';
