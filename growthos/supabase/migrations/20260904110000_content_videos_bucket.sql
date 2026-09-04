-- Bucket public pour les vidéos rendues par worker.py : video_url devient
-- une vraie URL partageable au lieu d'un chemin local à la machine du
-- worker. Écriture réservée à service_role (seul worker.py écrit, RLS par
-- défaut = deny, service_role la contourne) — aucune policy INSERT/UPDATE/
-- DELETE nécessaire. Lecture publique via /object/public/... qui contourne
-- RLS sur les buckets `public=true`, donc pas de policy SELECT non plus.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('content-videos', 'content-videos', true, 209715200, array['video/mp4'])
on conflict (id) do nothing;
