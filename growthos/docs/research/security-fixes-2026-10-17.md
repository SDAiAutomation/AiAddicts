# Correctifs de confidentialité — 17 octobre 2026

## État exact

Correctifs locaux implémentés et testés dans les deux dépôts. **Pas de déploiement ni de modification de la configuration de production. Le bucket content-videos reste public.**

La demande « corrige tout » autorise cette intervention ciblée frontend/backend au-delà de la répartition habituelle avec Claude. Aucun lot produit parallèle n'a été lancé.

## Changements

- Web : nouvelle route `GET /api/content/:id/media?asset=...`. Vérification de session, lecture de l'item sous RLS et liaison stricte UUID/chemin avant signature par le client service. Les chemins arbitraires, URL étrangères, traversées de répertoire et contenus non visibles sont refusés. Aucune policy Storage permissive ajoutée.
- Lecture vidéo, rognage visuel, aperçu TikTok et miniatures passent par cette route. Les anciennes URL en base restent des références stables ; aucun jeton signé n'est persisté.
- Export vidéo/sous-titres : vérification du contenu et de sa version, puis URL signée avec nom de téléchargement. La route refuse un fichier d'un autre contenu, même s'il était présent dans une réponse inattendue de la base.
- Liens signés valables cinq minutes, redirections privées `no-store` et `no-referrer`. Un lien signé copié reste utilisable jusqu'à expiration. Un lecteur resté ouvert au-delà de l'expiration peut nécessiter de recharger la page.
- Publication YouTube/TikTok et rognage Python : téléchargement via `/object/authenticated/`, avec clé serveur uniquement après validation de l'origine ; aucune redirection suivie. Limites existantes de taille, temps et média conservées.
- Les nouveaux uploads Generate utilisent `cache-control: 0` au lieu d'un an. Les fichiers déjà récupérés par des tiers ou conservés dans d'anciens caches ne peuvent pas être rendus secrets rétroactivement.
- `scripts/activate_private_generate.py` utilise l'API Storage pour la bascule et relit le bucket. Lecture seule par défaut ; activation conditionnée à trois options explicites. Aucun SQL direct dans les tables internes Storage.
- Le test `scripts/private-content-media.test.mjs` est intégré au `npm test` du frontend.

## Validation

- 177 tests frontend distincts réussis (176 dans le lot initial, puis le nouveau cas de téléchargement privé dans une relance de 6 tests).
- 38 tests Python réussis : source du rognage, arguments de découpe et crédits.
- TypeScript sans émission : réussi.
- `npm run build` : réussi, route `/api/content/[id]/media` présente.
- ESLint des huit fichiers TypeScript/TSX nouveaux/modifiés : réussi.
- `git diff --check` : réussi dans les deux dépôts.
- Script de bascule exécuté en lecture seule : `content-videos public=True`, aucun changement appliqué.
- Pas de validation navigateur connecté ni de lecture réelle d'un fichier Generate après bascule : l'accès au déploiement est bloqué. Les contrôles de routes utilisent des mocks ; ne pas les présenter comme un test d'intrusion de production.

## Alertes Supabase requalifiées

### pg_net

Extension non déplaçable (`extrelocatable=false`), objets appartenant à supabase_admin ; le cron actif `faceloop-tick` l'utilise. La plateforme ne permet pas la révocation ciblée attendue et une suppression casserait le cron. Aucun changement arbitraire appliqué.

Contrôle HTTP réel avec clé anon : demande du schéma `net` à la Data API refusée `406/PGRST106`, donc schéma non exposé. Aucune requête en attente ni aucun en-tête secret lu.

Conserver `net` hors des schémas API exposés et réserver les identifiants SQL aux services de confiance. L'alerte de placement reste une contrainte plateforme, pas une preuve de vulnérabilité via Inspecter.

Référence : https://supabase.com/docs/guides/troubleshooting/revoking-access-to-pg_net-objects-has-no-effect-0bbc16

### restore_content_version

Définition active relue : contrôle du rôle owner/strategist/editor dans l'organisation du contenu avant mutation ; version liée au même contenu ; restauration bornée aux états autorisés, hors rognage en cours. Son accès utilisateur est intentionnel. Ne pas supprimer ses permissions pour masquer l'advisor et casser la restauration.

### Mots de passe compromis

Toujours désactivé. Le connecteur Supabase disponible n'expose pas la configuration Auth. Activer dans [Supabase Auth](https://supabase.com/dashboard/project/lclesqfokgetznhepgmj/auth/providers), puis relancer l'advisor. Une éventuelle restriction de forfait doit être présentée à l'utilisateur avant tout changement payant.

Référence : https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

## Déploiement restant

Vercel trouve le projet `growthos-web`, mais la lecture des déploiements de son équipe retourne **403 forbidden**, scope `sdaiautomations-projects`. Aucune inspection/diff de production fiable possible avec cette connexion. CLI absent et `npx --no-install vercel` échoue `ENOTCACHED`. Réautoriser la connexion pour cette équipe avant de reprendre. Ce refus vient de Vercel, pas d'une demande d'approbation du code.

Ordre requis :

1. Déployer le frontend corrigé sur le projet et vérifier la nouvelle route avec une session autorisée, une session étrangère et sans session. Tester vidéo, miniature, original et export de version/sous-titres.
2. Déployer le worker contenant le téléchargement authentifié et le nouveau réglage de cache. Vérifier le rognage sans lancer de publication externe non demandée.
3. Après ces preuves, depuis le dépôt moteur : `venv/Scripts/python.exe scripts/activate_private_generate.py --activate --web-verified --worker-verified`.
4. Vérifier qu'un ancien lien public échoue sans session et qu'un nouveau lien signé fonctionne. Vérifier les en-têtes/caches du Storage/CDN ; des copies précédemment mises en cache peuvent nécessiter une invalidation côté hébergeur. Ne pas certifier la confidentialité à partir du seul champ `public=false`.
5. Activer la protection des mots de passe et relire les advisors.

Ne pas activer le bucket avant les déploiements : l'ancien frontend et l'ancien worker utilisent encore les URL publiques. Les nouveaux lecteurs authentifiés et la signature fonctionnent aussi avant la bascule, permettant cet ordre progressif.

Référence accès privé Storage : https://supabase.com/docs/guides/storage/serving/downloads
