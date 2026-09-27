-- Suppression d'un montage par l'utilisateur (DELETE /api/autoedit/jobs/:id).
-- L'API efface d'abord la source et le rendu (service_role), puis la ligne
-- avec le client de l'utilisateur : cette policy est la garde atomique.
-- Statuts supprimables : ceux que le worker ne reprend jamais (terminés,
-- en échec) et l'envoi pas encore confirmé. Un job en file ou en cours de
-- traitement reste intouchable. Les écritures credits_ledger liées sont
-- conservées (related_autoedit_job_id passe à null).
create policy "autoedit_jobs_delete_finished" on public.autoedit_jobs for delete
  using (
    status in ('uploading', 'review', 'completed', 'failed')
    and internal.has_org_role(organization_id, array['owner', 'strategist', 'editor'])
  );

grant delete on public.autoedit_jobs to authenticated;
