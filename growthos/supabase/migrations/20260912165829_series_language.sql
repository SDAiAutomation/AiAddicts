-- Langue des épisodes d'une série (comme visual_style / voice_id / caption_style) :
-- reprise telle quelle dans le script de chaque épisode généré
-- (api/cron/series), et paramètre le prompt de génération IA (ai-actions.ts
-- buildBasePrompt) ainsi que la voix off (ElevenLabs eleven_multilingual_v2,
-- qui détecte la langue depuis le texte lui-même).
-- Null = défaut moteur ("fr").

alter table series add column language text
  check (language is null or language in ('fr', 'en', 'es', 'de', 'it', 'pt'));

comment on column series.language is
  'Langue des scripts générés pour les épisodes de la série. Null = défaut moteur (fr).';
