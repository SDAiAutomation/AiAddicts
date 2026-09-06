-- Contrôle qualité automatique (engine/quality.py) : `quality_score` existait
-- déjà (0-100) mais rien ne l'écrivait. On ajoute la liste des motifs qui
-- expliquent un score bas, affichée sur /content/[id] quand l'item est en
-- `quality_check`. Écrite par le worker (service_role) uniquement, comme les
-- autres colonnes de pipeline.

alter table content_items
  add column quality_flags jsonb not null default '[]'::jsonb;

comment on column content_items.quality_flags is
  'Motifs de pénalité du contrôle qualité auto (voix off courte, scène sans visuel, etc.). Vide si score plein.';
