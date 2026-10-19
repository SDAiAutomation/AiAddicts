# Vérification sécurité « Inspecter » — 17 octobre 2026

## Portée

Revue ciblée du code local et lecture des catalogues de la base Supabase active `growthos`. Aucun changement de production, aucune consommation IA, aucune modification de données utilisateur. Ce contrôle ne certifie pas toute la sécurité du produit ni la correspondance du code local avec les versions web/worker déployées. Aucun test d'intrusion HTTP avec deux comptes réels n'a été effectué.

Révisions : moteur `545ab48524a858fb63a99336cb7754afbb2c29e5`, web `e2c659cbaf92d8a637a06179cb426f01b56b3da5`.

## Protections constatées

- Base active : RLS activée sur les 25 tables observées des schémas public/audit. Les politiques de contenus et organisations consultées limitent les lectures aux organisations du membre et les écritures aux rôles autorisés. L'activation seule de RLS ne prouve pas toutes les règles applicatives.
- Droits SQL actifs : authenticated ne peut modifier ni abonnement, ni solde, ni quotas dans organizations (seul name est modifiable). credits_ledger est accessible en lecture seulement. Les colonnes contenant les tokens OAuth chiffrés ne sont pas lisibles par ce rôle.
- Le trigger `a0_guard_content_items_internal_columns` est présent et actif en production. Sa définition protège notamment completed_generations, video_url, original_video_url et les rapports internes contre INSERT/UPDATE directs des clients. Cela ferme le chemin de falsification du compteur décrit dans SEC-02 du rapport du 11 octobre.
- Code local : le client service Supabase importe server-only ; seuls URL et clé anon Supabase sont référencés en NEXT_PUBLIC dans src. Le webhook Stripe vérifie la signature du corps brut.
- Scan heuristique des fichiers texte suivis : 370 côté moteur et 464 côté web, aucun motif de secret détecté. Exclusions : historique Git, fichiers ignorés, secrets de déploiement, bundles réellement servis. Ce résultat ne prouve pas l'absence de tout secret.
- SEC-01 : engine/trim.py contrôle désormais origine et chemin liés au contenu, interdit les redirections, borne taille/durée et valide le média ; protocoles du décodeur restreints aux fichiers locaux.
- SEC-03 : generateSeriesEpisode vérifie isInternalCall avant le fournisseur ; contexte AsyncLocalStorage réservé au serveur. L'export reste une Server Action, mais l'appel réseau ne dispose pas du contexte interne. Tests du contexte et de la présence des gardes réussis ; le contrôle statique de présence n'est pas une preuve exhaustive d'autorisation.
- SEC-04 : les actions YouTube/TikTok de connexion/déconnexion relues filtrent organization_id ; la publication YouTube relue vérifie accountInOrg. Aucun nouvel exercice complet multi-organisations sur tous les callbacks n'a été effectué.

## Réserves concrètes

1. **Confidentialité Generate :** le bucket `content-videos` est public en production. Une personne possédant l'URL d'une vidéo peut la lire sans connexion. Cela n'autorise pas à modifier les comptes ou crédits, mais un lien ne constitue pas un contrôle d'accès. Les buckets autoedit-sources, autoedit-results et content-assets sont privés. Si les vidéos Generate doivent être privées avant publication, prévoir une migration vers stockage privé et liens signés, avec adaptation du rendu, du téléchargement et des publications ; ne pas basculer le bucket sans ces adaptations.
2. **Mots de passe compromis :** protection désactivée selon l'advisor actuel. À activer selon les possibilités du projet : https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection
3. **Durcissement Supabase :** pg_net reste dans public. Alerte à traiter, sans exploitation démontrée : https://supabase.com/docs/guides/database/database-linter?lint=0014_extension_in_public
4. **Fonction privilégiée :** l'advisor signale restore_content_version accessible à authenticated. Le précédent audit avait vérifié ses contrôles internes ; ils n'ont pas été réaudités dans cette passe. Une alerte n'est pas à elle seule une faille : https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable
5. Les tables admin_actions, content_assets et security_rate_limits sont signalées RLS sans policy : refus utilisateur par défaut, cohérent avec un usage serveur ; ne pas ajouter une policy permissive pour faire disparaître ces messages.

## Validation exécutée

- 30 tests Python réussis : tests.test_trim_source_guard et tests.test_repo_credits.
- 28 tests frontend distincts réussis : internal-call-guard, generation-credit, admin, autoedit-api. Deux tests étaient initialement bloqués par spawnSync git EPERM ; relance autorisée de la suite internal-call-guard : 4/4 réussis.
- Ces tests sont principalement locaux et simulés ; ils ne remplacent pas des essais de permissions sous plusieurs sessions en environnement isolé.

## Conclusion

Les protections vérifiées empêchent les modifications directes du solde et du plan depuis le navigateur. Les quatre problèmes de l'ancien audit ont désormais des correctifs visibles sur les chemins relus ; la garde SQL est confirmée active en ligne. Ne pas présenter cela comme une garantie globale : confidentialité des liens Generate, protection des mots de passe et validation des versions réellement déployées restent à traiter/vérifier. Corrections backend/frontend à coordonner avec Claude conformément aux instructions de propriété du dépôt.

Référence de contrôle RLS : https://supabase.com/docs/guides/database/postgres/row-level-security
