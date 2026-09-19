-- Miniature JPEG (~20 Ko) de la vidéo, stockée dans le bucket content-videos.
-- Les listes (/content, dashboard) affichaient une balise <video> par ligne pour
-- montrer un premier frame, ce qui re-téléchargeait des Mo par vidéo à chaque
-- affichage et a dépassé le quota d'egress Supabase. Colonne additive,
-- nullable, écrite par le worker (service_role) ; NULL = pas de miniature (le
-- front affiche une icône).

alter table public.content_items
  add column poster_url text;

comment on column public.content_items.poster_url is
  'URL publique de la miniature JPEG de la vidéo (engine/poster.py). NULL si non générée.';
