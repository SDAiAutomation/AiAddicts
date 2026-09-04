-- Phase 2 : le front insère un content_item en status='queued' (script déjà
-- construit), worker.py (engine/) le récupère, génère la vidéo, et remet le
-- statut à jour. 'generating' marque un job réclamé par un worker.

alter table content_items drop constraint content_items_status_check;
alter table content_items add constraint content_items_status_check
  check (status in ('idea','script','queued','generating','video','quality_check','published','failed'));

alter table content_items add column error text;
alter table content_items add column requested_by uuid references profiles(id);

comment on column content_items.error is
  'Message d''erreur du dernier run worker en échec (status=failed). Effacé au prochain succès.';
comment on column content_items.requested_by is
  'Utilisateur qui a mis ce contenu en file de génération (status=queued). Null pour les items créés hors front (CLI).';
