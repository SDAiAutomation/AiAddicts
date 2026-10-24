-- PENDING, NOT APPLIED: private bucket for approved animated-story asset packs (Gate 4, R1).
--
-- Read only by the worker with the service role (same model as `autoedit-sources`): no policy is created on
-- storage.objects for this bucket, so authenticated and anonymous users can neither list nor read nor write it.
-- Objects: <pack_id>/manifest.json and <pack_id>/<sprite>.png (see engine/story_animation/pack_fetch.py).
-- Publishing a pack is a manual, reviewed step with the service role; nothing in the product writes here.
--
-- Apply first on an isolated Supabase branch, never directly on the project shared by Preview and Production.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('story-packs', 'story-packs', false, 12582912, array['image/png', 'application/json'])
on conflict (id) do nothing;

-- Safety net: if the bucket already existed and was public, make it private.
update storage.buckets set public = false where id = 'story-packs';
