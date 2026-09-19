-- Les miniatures (<content_item_id>.jpg, voir engine/poster.py) vivent dans le
-- même bucket public que les vidéos : on autorise image/jpeg en plus de
-- video/mp4. Limite de taille et visibilité inchangées.
update storage.buckets
set allowed_mime_types = array['video/mp4', 'image/jpeg']
where id = 'content-videos';
