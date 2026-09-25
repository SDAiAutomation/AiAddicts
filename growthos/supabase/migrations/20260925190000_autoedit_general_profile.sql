alter table public.autoedit_jobs drop constraint if exists autoedit_jobs_profile_check;
alter table public.autoedit_jobs
  add constraint autoedit_jobs_profile_check check (profile in ('sports', 'general'));

comment on column public.autoedit_jobs.profile is
  'Profil AutoEdit : sports sans sous-titres, general avec transcription de la parole.';
