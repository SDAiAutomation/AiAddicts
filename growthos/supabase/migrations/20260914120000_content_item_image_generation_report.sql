-- Suivi coût/QC du pipeline d'images (engine/image_model_router.py,
-- engine/image_quality_control.py) : coût estimé total, version de prompt/
-- style bible, détail par scène (modèle, qualité, tentatives, score QC,
-- revue manuelle nécessaire ou non). Colonne additive, nullable : absente
-- (NULL) tant que le contrôle qualité vision (IMAGE_QC_ENABLED) n'est pas
-- activé ou qu'aucune scène n'a été (re)générée sur ce run. Écrite par le
-- worker (service_role) uniquement, comme les autres colonnes de pipeline.

alter table content_items
  add column image_generation_report jsonb;

comment on column content_items.image_generation_report is
  'Rapport agrégé de génération d''images : coût estimé, promptVersion/styleBibleVersion, détail par scène (modèle, qualité, tentatives, qualityScore, manualReview). NULL si aucune scène (re)générée ce run.';
