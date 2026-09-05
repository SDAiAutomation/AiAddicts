-- Point trouvé en testant le workflow GitHub Actions (2026-09-05) : un
-- worker tué en plein travail (kill, crash, coupure réseau) laisse le
-- content_item bloqué en status='generating' pour toujours — claim_queued_item
-- ne regarde que status='queued', rien ne récupère un item orphelin.
--
-- `updated_at` (mis à jour par le code applicatif à chaque étape/réclamation,
-- pas de trigger générique dans ce schéma) permet de détecter l'ancienneté
-- d'un 'generating' pour le remettre en file — voir engine/repo.py.

alter table content_items add column updated_at timestamptz not null default now();

comment on column content_items.updated_at is
  'Bumped par le worker à chaque réclamation/étape de génération. Sert à détecter un status=generating orphelin (worker mort en plein travail) et le remettre en queued — voir repo.reclaim_stale_generating_items().';
