-- La page /content/[id] se rafraîchit déjà (polling 4s, generate-section.tsx)
-- pendant status='queued'/'generating', mais n'affiche qu'un message fixe :
-- rien ne distingue "voix off" de "rendu vidéo" côté site, seul le terminal
-- de worker.py a le détail. Cette colonne fait remonter l'étape courante
-- jusqu'au front, sans changer le contrat de statut existant.

alter table content_items add column generation_step text;

comment on column content_items.generation_step is
  'Étape courante pendant status=generating (ex: "Voix off (2/5)"), affichée sur /content/[id]. Effacée à la fin du run (succès ou échec), null hors génération.';
