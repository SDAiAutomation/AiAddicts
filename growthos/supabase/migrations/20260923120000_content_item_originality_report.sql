-- Diagnostic d'originalité (engine/originality.py) : comparaison du script
-- aux ~20 dernières vidéos du même compte (concept, personnage, situation,
-- hook, progression, twist, conclusion, vocabulaire). Capacité NOUVELLE et
-- OPT-IN (ORIGINALITY_CHECK_ENABLED=false par défaut). Diagnostic heuristique,
-- jamais une certification de doublon ni de l'éligibilité à la monétisation.
-- Colonne additive, nullable, écrite par le worker (service_role) ; NULL =
-- non vérifié (capacité désactivée, ou échec best-effort).

alter table public.content_items
  add column originality_report jsonb;

comment on column public.content_items.originality_report is
  'Diagnostic de ressemblance avec les vidéos précédentes du compte : {model, comparedCount, historyAvailable, tooSimilar, overallSimilarity, dimensions:[{name,similarity,matchedVideoIds,explanation}], suggestion}. NULL si non vérifié. Ne certifie jamais un doublon ni l''éligibilité à la monétisation.';
