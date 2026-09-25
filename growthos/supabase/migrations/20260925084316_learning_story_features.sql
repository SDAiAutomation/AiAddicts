-- Mémoire éditoriale v2 (engine/learning.py, refresh_learning.py).
--
-- story_features : classification mise en cache d'une vidéo pour
-- l'apprentissage ({"archetype", "hookType", "model", "version"}), calculée
-- une seule fois par un modèle texte puis réutilisée à chaque relevé.
-- Écrite uniquement par le worker (service role).
--
-- insights.kind 'archetype' : performance par archétype narratif (liste de
-- PRODUCT_DOCTRINE.md), qui remplace l'ancien regroupement par titre exact
-- ('topic', une vidéo par groupe, qui poussait à refaire la même vidéo).

alter table content_items add column if not exists story_features jsonb;

alter table insights drop constraint if exists insights_kind_check;
alter table insights add constraint insights_kind_check
  check (kind in ('hook', 'format', 'topic', 'schedule', 'archetype'));
