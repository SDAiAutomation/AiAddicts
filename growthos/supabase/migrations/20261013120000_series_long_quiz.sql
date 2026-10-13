-- Extend the existing quiz series configuration for the long pilot.
alter table public.series drop constraint if exists series_quiz_config_shape;

alter table public.series add constraint series_quiz_config_shape check (
  (content_format = 'standard' and quiz_config is null)
  or
  (content_format = 'quiz'
    and jsonb_typeof(quiz_config) = 'object'
    and coalesce(quiz_config->>'topic', '') <> ''
    and quiz_config->>'recipe' in ('quick', 'true_false', 'riddle', 'logo', 'impossible', 'long')
    and case when quiz_config->>'recipe' = 'long'
      then (quiz_config->>'question_count')::integer between 10 and 30
      else (quiz_config->>'question_count')::integer between 1 and 7 end
    and (quiz_config->>'countdown_seconds')::integer between 1 and 10
    and quiz_config->>'difficulty' in ('easy', 'medium', 'hard', 'progressive'))
);
