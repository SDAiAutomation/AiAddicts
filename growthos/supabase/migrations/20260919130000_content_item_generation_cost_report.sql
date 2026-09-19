-- Coût variable d'une génération vidéo (images OpenAI + voix ElevenLabs), en $ :
-- {currency, images:{count,cost,tokens}, voice:{characters,cost},
-- totalEstimatedCost, missingRates}. Sert à vérifier la marge des forfaits
-- (Starter/Pro) sur des chiffres réels plutôt que des estimations. Colonne
-- additive, nullable, écrite par le worker (service_role) uniquement ; NULL
-- pour les vidéos générées avant ce suivi ou re-rendues sans rien de neuf.

alter table content_items
  add column generation_cost_report jsonb;

comment on column content_items.generation_cost_report is
  'Coût estimé de la génération en $ : images (tokens réels x tarifs env), voix (caractères x tarif env), total, et missingRates listant les tarifs non configurés. NULL si non mesuré.';
