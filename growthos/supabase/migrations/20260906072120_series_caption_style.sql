-- Style des sous-titres par série (comme visual_style / voice_id) : repris
-- tel quel dans le script de chaque épisode généré (api/cron/series), puis
-- appliqué par le pipeline (engine/captions._CAPTION_STYLES).
-- Null = défaut moteur ("bold_stroke").

alter table series add column caption_style text
  check (caption_style is null or caption_style in
    ('bold_stroke', 'sleek', 'boxed', 'neon', 'word_pop'));

comment on column series.caption_style is
  'Style de sous-titres brûlés pour les épisodes de la série. Null = défaut moteur.';
