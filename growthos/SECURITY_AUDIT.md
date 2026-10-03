# Audit de sécurité Faceloop

Date : 2026-10-03  
Référentiel : `Securite_Faceloop_Claude_Codex.md`, cible OWASP ASVS L2. La version stable vérifiée au début de l'audit est ASVS 5.0.0.  
Commits examinés : backend `8463874`, frontend `359943c`. Les modifications locales préexistantes de `AGENTS.md` et `CLAUDE.md` n'ont pas été auditées comme code produit et n'ont pas été modifiées.

## Conclusion exécutive

Faceloop ne doit pas être déclaré prêt pour une mise en production commerciale sur la base de cet audit.

Deux défauts observés sont bloquants :

1. **SEC-001 — SSRF et transitions privilégiées via `content_items` (élevé).** Le rôle `authenticated` reçoit `UPDATE` sur toutes les colonnes de `public.content_items` dans `supabase/migrations/20261002160143_harden_billing_quotas_and_privileges.sql`. La RLS limite la ligne au tenant, mais ne limite pas les colonnes ni les transitions. Un membre autorisé à éditer son contenu peut donc appeler directement PostgREST pour modifier `video_url`, `original_video_url`, `trim_status`, `status`, `completed_generations`, `requested_by` et d'autres champs réservés au serveur. Le worker charge ensuite `video_url`/`original_video_url` avec `requests.get` dans `engine/trim.py` sans politique SSRF. Ce chemin peut provoquer une requête du worker vers loopback, réseau privé, link-local ou metadata cloud. Il permet aussi de contourner les transitions applicatives et de fausser le compteur de générations.
2. **SEC-002 — vidéos Generate publiques par défaut (élevé).** `supabase/migrations/20260904110000_content_videos_bucket.sql` crée `content-videos` avec `public=true`. Les URL sont permanentes et lisibles sans autorisation. Les scripts et vidéos sont traités comme privés dans le modèle de menace du référentiel ; une URL difficile à deviner n'est pas une autorisation.

Le code comporte néanmoins des protections solides : sessions Supabase vérifiées par `auth.getUser()`, RLS tenant, révocation des RPC financières aux rôles client, quotas atomiques et fail-closed, réservations de crédits avant dépense, signature Stripe sur corps brut, CSP à nonce et HSTS, chiffrement AES-256-GCM des tokens sociaux, crons protégés par comparaison constante et buckets AutoEdit privés avec URL signées.

## Périmètre et méthode

Observé statiquement :

- migrations et tests SQL Supabase ;
- Server Actions, Route Handlers, proxy, OAuth, Stripe, cron et AutoEdit du frontend Next.js ;
- workers Python, appels réseau, stockage et invocation FFmpeg du backend ;
- fichiers d'environnement par **nom de variable uniquement**, `.gitignore`, fichiers suivis et motifs de secrets plausibles ;
- dépendances npm de production ;
- suites de régression disponibles.

Non observé : configuration effective du projet Supabase/Vercel/Stripe/Google/TikTok/GitHub, policies réellement déployées, grants effectifs, WAF, MFA, sauvegardes, journaux/alertes, réseau du worker et secrets historiques complets. Aucun test intrusif n'a été lancé contre la production ni un tiers.

## Constats détaillés

### SEC-001 — SSRF et champs privilégiés modifiables via l'API Supabase

- Surface : Data API Supabase, `content_items`, file de rognage, worker.
- Statut : défaut avéré.
- Sévérité : **élevée**, bloquante avant production. Un utilisateur authentifié agit depuis le réseau et l'identité du worker ; l'impact dépend du réseau accessible au runner.
- Preuve minimale : grant large `grant select, insert, update, delete on table public.content_items to authenticated`; policy UPDATE fondée sur le rôle du tenant mais sans `WITH CHECK` explicite dans la migration initiale ; `claim_trim_job()` lit les URL de la ligne ; `_download()` exécute `requests.get(url, stream=True, timeout=180)`.
- Correction minimale : révoquer l'UPDATE table-wide ; accorder uniquement les colonnes éditables ou, de préférence, exposer des RPC étroites pour édition, mise en file, rognage et publication. Déplacer les transitions de statut et compteurs dans des fonctions transactionnelles server-only. Le worker ne doit jamais télécharger une URL arbitraire stockée par le client : stocker un chemin de bucket validé et télécharger via Storage, ou appliquer une allowlist stricte plus filtrage DNS/IP/redirections et egress réseau.
- Responsable : Claude Code pour migration/RPC/worker ; Codex pour adapter les actions frontend au contrat.
- Test de régression : sous rôle `authenticated`, l'UPDATE direct de `video_url`, `original_video_url`, `trim_status`, `status`, `completed_generations`, `credits_reserved`, `requested_by` échoue ; les RPC légitimes passent ; une URL loopback, privée, link-local, IPv6 locale et une redirection vers ces cibles ne déclenchent aucune connexion.

### SEC-002 — bucket Generate public

- Surface : Supabase Storage `content-videos`.
- Statut : défaut avéré.
- Sévérité : **élevée**, bloquante pour tout contenu supposé privé.
- Preuve minimale : migration `20260904110000_content_videos_bucket.sql`, bucket `public=true`, commentaires indiquant une lecture publique sans policy SELECT ; `engine/storage.py` retourne `get_public_url`.
- Correction minimale : bucket privé, chemins tenant/item, stockage du chemin plutôt que d'une URL publique, génération d'URL signée courte uniquement après contrôle de tenant. Prévoir migration des objets et compatibilité des vidéos déjà rendues.
- Responsable : Claude Code pour Storage/backend ; Codex pour génération des liens autorisés et états expirés.
- Test de régression : accès anonyme refusé ; B ne peut pas signer/lire A ; lien expiré refusé ; preview, téléchargement, TikTok et YouTube continuent avec une URL signée fraîche.

### SEC-003 — state OAuth rejouable pendant sa durée de vie — corrigé côté frontend

- Surface : OAuth YouTube et TikTok.
- Statut : corrigé dans le worktree frontend, vérification de déploiement restante.
- Sévérité : **moyenne**. Le state est signé, lié à l'utilisateur et limité à dix minutes, mais il n'est pas enregistré ni consommé une seule fois.
- Preuve minimale : `src/lib/youtube/oauth-state.ts` et `src/lib/tiktok/oauth-state.ts` encodent `accountId.userId.timestamp` avec HMAC ; aucune nonce persistée/consommée ; les tests vérifient liaison/fraîcheur, pas le rejeu.
- Correction appliquée : nonce aléatoire de 256 bits dans le state ; empreinte liée au navigateur dans un cookie `HttpOnly`, `Secure` en production, `SameSite=Lax`, TTL dix minutes ; consommation avant l'échange de token. Un state rejoué, d'une autre session, ancien ou sans nonce est refusé. PKCE reste à évaluer selon chaque fournisseur.
- Responsable : Codex frontend, contrat OAuth partagé validé avec backend si stockage dédié.
- Test : régressions statiques et unitaires sur nonce, liaison navigateur, consommation avant appel fournisseur et rejet des anciens payloads ; test E2E fournisseur/staging restant.

### SEC-004 — anti-abus d'authentification non démontré

- Surface : login, signup, confirmation/récupération Supabase.
- Statut : configuration non vérifiée / risque probable.
- Sévérité : **moyenne**.
- Preuve minimale : les actions `login/actions.ts` et `signup/actions.ts` n'appellent pas le limiteur partagé ; aucune preuve accessible de limites Supabase, CAPTCHA, MFA ou détection credential stuffing. Les erreurs de login sont génériques, ce qui réduit l'énumération.
- Correction minimale : documenter et tester les réglages Supabase Auth, limites par compte normalisé + IP fiable + session, CAPTCHA adaptatif, MFA obligatoire pour administrateurs, procédures de révocation.
- Responsable : propriétaire infrastructure/auth.
- Test : rafales contrôlées en staging, reset rejoué, token expiré/falsifié, session révoquée et retour externe.

### SEC-005 — configuration et tests DB effectifs non vérifiés

- Surface : Supabase déployé.
- Statut : non vérifié.
- Sévérité : **élevée tant que non vérifiée**, car la sécurité dépend des migrations et grants réellement appliqués.
- Preuve minimale : tests pgTAP présents (`supabase/tests/security_hardening.test.sql`) mais CLI Supabase et Docker indisponibles dans l'environnement ; aucun accès au projet déployé ni aux advisors.
- Correction minimale : exécuter sur une base jetable au commit cible : migrations, `supabase test db`, inventaire `pg_policies`, `information_schema.role_*_grants`, fonctions `SECURITY DEFINER`, vues, buckets et advisors. Répéter avec comptes A/B et rôles owner/strategist/editor/viewer.
- Responsable : Claude Code / propriétaire Supabase.

### SEC-006 — suite frontend rouge par dérive du test admin — corrigé

- Surface : CI/régressions.
- Statut : corrigé.
- Sévérité : **faible**, mais la CI doit être verte avant release.
- Preuve minimale : `npm test` : 182 tests passent, 1 échoue. Le test cherche l'ancien nom `consumeRateLimit`, alors que l'action appelle désormais `checkRateLimit` après `requireAdmin`; l'ordre de sécurité observé reste correct.
- Correction appliquée : assertion mise à jour pour `checkRateLimit`; la suite complète passe.
- Responsable : Codex.

### SEC-007 — scan de dépendances Python absent

- Surface : chaîne de dépendances backend.
- Statut : non vérifié.
- Sévérité : **moyenne**.
- Preuve minimale : `pip-audit` absent ; `pytest` absent du Python système et du venv. `npm audit --omit=dev` a trouvé 0 vulnérabilité sur 162 dépendances de production, mais ce résultat ne couvre ni Python ni l'exploitabilité runtime.
- Correction minimale : CI avec environnement Python reproductible, versions bornées/lock, `pip-audit` ou équivalent, tests backend, traitement documenté des avis.
- Responsable : Claude Code / infrastructure CI.

### SEC-008 — limites d'upload et isolation worker partielles

- Surface : AutoEdit upload et décodage média.
- Statut : partiellement conforme, contrôles critiques non vérifiés.
- Sévérité : **moyenne**, AutoEdit étant désactivé par défaut.
- Preuve : buckets privés, MIME et taille bucket, chemin lié à org/job, résultats privés et limite de jobs actifs. Aucune preuve de magic-byte/ffprobe avant décodage, quarantaine/antimalware, worker non-root, limites CPU/RAM/disque, réseau des décodeurs ou nettoyage garanti.
- Correction minimale : préflight média isolé, limites ffprobe/ffmpeg, timeouts/process limits, refus des playlists/protocoles réseau, quotas stockage et purge testée.
- Responsable : Claude Code.

### SEC-009 — déduplication Stripe partielle

- Surface : webhook Stripe.
- Statut : partiellement conforme.
- Sévérité : **moyenne**.
- Preuve : signature officielle sur corps brut ; crédits pack/plan idempotents via références uniques et fonctions transactionnelles. Il n'existe pas de registre générique des `event.id`; certaines mises à jour d'abonnement sont naturellement idempotentes mais l'ordre complet, remboursements et litiges ne sont pas couverts par des tests accessibles.
- Correction minimale : journal transactionnel des événements Stripe, statuts de traitement, tests replay/out-of-order/refund/dispute, vérification que le customer/subscription appartient à l'organisation attendue.
- Responsable : Codex pour route/UX, Claude Code pour transaction/ledger partagé.

### SEC-010 — détection/réponse et continuité non démontrées

- Surface : exploitation.
- Statut : non vérifié.
- Sévérité : **moyenne à élevée** selon exposition.
- Preuve : logs applicatifs et table d'audit existent, mais aucune preuve accessible d'alertes livrées, kill switches, runbook incident, rotation testée, sauvegarde/restauration, RPO/RTO ou simulation de clé compromise.
- Correction minimale : lot exploitation dédié avec preuves datées.
- Responsable : propriétaire infrastructure/produit.

## Protections conformes avec preuve locale

- Auth serveur : `requireOrg`, layout protégé et proxy utilisent `supabase.auth.getUser()` plutôt qu'un simple décodage JWT.
- Isolation tenant : policies RLS fondées sur memberships pour les tables principales ; AutoEdit vérifie aussi `organization_id` avant opérations service-role.
- Secrets : `SUPABASE_SERVICE_ROLE_KEY`, Stripe/OpenAI/OAuth restent sans préfixe `NEXT_PUBLIC_`; clients privilégiés marqués `server-only`; `.env` et `.env.local` ignorés. Aucun secret plausible Stripe (`sk_*`/`whsec_*` de longueur réelle) trouvé dans les arbres suivis examinés. Cela n'est pas un scan historique exhaustif.
- SQL : appels applicatifs via SDK/RPC paramétrés ; fonctions financières récentes bornent leurs paramètres, verrouillent les lignes et sont exécutables uniquement par `service_role`.
- Commandes média : FFmpeg est appelé avec une liste d'arguments et `shell=False` dans `_run`; l'unique `shell=True` observé lance la constante Windows `chcp 65001`, sans entrée utilisateur.
- Navigateur : CSP à nonce en production, `frame-ancestors 'none'`, `object-src 'none'`, HSTS, nosniff, referrer et permissions policy.
- Génération : limite partagée en base, quota mensuel atomique, comportement fail-closed, réservation de crédit avant appels payants et remboursements idempotents.
- Stripe : prix sélectionnés côté serveur par lookup key allowlistée, checkout réservé au owner, webhook signé sur corps brut, crédits accordés par RPC service-role idempotente.
- Cron : secret obligatoire et comparaison temporelle constante.
- Tokens sociaux : AES-256-GCM au repos ; colonnes chiffrées retirées du rôle `authenticated`.
- AutoEdit : fonctionnalité désactivée par défaut, buckets source/résultat privés, upload lié au tenant/job, URL signées, limite de concurrence atomique.

## Plan de correction par lots

### Lot 0 — blocage immédiat avant production

1. Retirer les grants larges de `content_items`; RPC étroites et tests de colonnes/transitions.
2. Éliminer l'URL arbitraire du worker et ajouter une politique SSRF + egress deny.
3. Passer `content-videos` en privé et migrer tous les consommateurs vers des URL signées.
4. Exécuter la matrice A/B et pgTAP sur la base candidate.

Critères de sortie : aucun UPDATE direct des champs serveur ; aucune connexion worker vers cibles interdites ; vidéo Generate anonyme/B refusée ; tests légitimes preview/download/publish verts ; advisors et matrice grants/policies archivés.

### Lot 1 — paiements, génération et identités

1. Registre transactionnel des événements Stripe et tests replay/out-of-order/refund/dispute.
2. State OAuth one-shot + PKCE si supporté.
3. Validation des réglages Auth, rate limits multi-dimensionnels et MFA admin.
4. Tests concurrents quotas/crédits et panne du limiteur en staging.

Critères de sortie : aucun double crédit/débit, aucun appel fournisseur après refus de budget, replay OAuth refusé, session révoquée refusée dans la borne documentée.

### Lot 2 — fichiers, worker et supply chain

1. Préflight magic bytes/ffprobe, limites ressources et protocoles FFmpeg.
2. Worker non-root, egress allowlist, secrets minimaux, nettoyage/rétention testés.
3. Audit Python et lock reproductible ; CI sécurité et suite backend.
4. Corriger le test admin obsolète.

Critères de sortie : corpus hostile refusé/borné ; absence de lecture locale/réseau depuis média ; scanners traités ; suites vertes.

### Lot 3 — exploitation et assurance

1. Alertes auth/tenant/dépenses/paiements/publications et test de livraison.
2. Kill switches génération/publication/intégrations.
3. Runbooks, rotation, sauvegarde/restauration, RPO/RTO et exercice.
4. Revue indépendante ciblée ASVS L2 avant lancement commercial large.

## Porte de mise en production

Bloquer tant que l'un des points suivants subsiste : SEC-001 ou SEC-002 non corrigé ; permissions DB déployées non vérifiées ; matrice A/B absente ; crédit/paiement concurrent non testé ; stockage privé non démontré ; dépense fournisseur possible lorsque quota/autorisation échoue ; risque critique/élevé sans dérogation datée et approuvée.

## Résultats de commandes et limites

- `npm audit --omit=dev --json` : 0 vulnérabilité déclarée sur 162 dépendances de production.
- `npm test` après corrections frontend : 185/185 succès, dont un test comportemental du state OAuth à usage unique.
- `pip-audit` : non exécuté, module absent.
- `pytest` backend : non exécuté, module absent dans les deux interpréteurs disponibles.
- `supabase test db` / advisors : non exécutés, CLI Supabase et Docker absents.
- Aucun test actif production, aucune tentative SSRF réelle, aucun brute force, aucun paiement réel.

Ce rapport établit des observations au commit indiqué. Il ne constitue ni une attestation ASVS complète ni une garantie de sécurité.
