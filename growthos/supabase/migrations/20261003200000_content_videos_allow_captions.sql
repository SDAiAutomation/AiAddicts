-- Lot L2 : le bucket content-videos n'acceptait que video/mp4 et image/jpeg,
-- l'upload des sous-titres .srt (export par version) était refusé. Idempotent.
update storage.buckets
set allowed_mime_types = (
  select array_agg(distinct m) from unnest(allowed_mime_types || array['text/plain']) as m
)
where id = 'content-videos'
  and allowed_mime_types is not null
  and not ('text/plain' = any(allowed_mime_types));
