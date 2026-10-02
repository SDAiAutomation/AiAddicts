-- Durcissement RLS suite à l'audit du 2026-10-02 (aucune fuite inter-organisation trouvée, deux points à corriger).
--
-- 1) `credits_ledger_owner_insert` permettait à n'importe quel owner d'insérer directement, via PostgREST,
--    une ligne dans credits_ledger avec un `delta`/`balance_after` ARBITRAIRE (non lié au vrai solde) : aucune
--    validation dans la policy. Vérifié : aucun code (web ni moteur) ne s'appuie sur cet insert direct, tous les
--    ajouts réels passent par des fonctions SECURITY DEFINER (grant_plan_credits, grant_pack_credits,
--    admin_grant_credits, atomic_credit_decrement/reservation…) qui contournent RLS. Supprimer la policy ne casse
--    donc rien côté app ; ça retire une façon de fabriquer un faux historique de crédits pour son propre org.
drop policy if exists credits_ledger_owner_insert on public.credits_ledger;

-- 2) `enforce_account_limit` est une fonction de TRIGGER (returns trigger), pas un RPC utilisable : l'appeler
--    directement via /rest/v1/rpc/enforce_account_limit lève une erreur Postgres plutôt que d'exécuter quoi que
--    ce soit (confirmé par lecture de sa définition). Mais elle est encore exposée à anon/authenticated via RPC,
--    flaguée par l'advisor de sécurité Supabase — la migration revoke_definer_rpc_from_api_roles l'avait oubliée.
revoke execute on function public.enforce_account_limit() from public, anon, authenticated;
