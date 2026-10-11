-- La table de provenance est append-only : le collecteur n'a besoin que d'inserer (et de relire pour
-- compter les lignes inserees). En production les privileges par defaut du projet donnaient aussi
-- update et delete a service_role (la branche testee ne les donnait pas) : on les retire pour que la
-- production corresponde a ce qui a ete teste et qu'une ligne enregistree ne soit jamais reecrite.
-- Aucune ligne ni aucune politique n'est touchee ; la suppression en cascade avec la video (cle
-- etrangere ON DELETE CASCADE) est executee par le proprietaire de la table et reste inchangee.
revoke update, delete on table public.youtube_metric_snapshots from service_role;
