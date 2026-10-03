# Registre des contrôles de sécurité Faceloop

Date d'observation : 2026-10-03  
Responsables : **FE** = Codex/frontend ; **BE** = Claude Code/backend ; **OPS** = propriétaire infrastructure/produit.  
Statuts : Conforme avec preuve, Non conforme, Non vérifié, Non applicable avec justification.

Les preuves détaillées et les constats SEC-001 à SEC-010 sont dans `SECURITY_AUDIT.md`.

## Développement

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| DEV01 | P0 | FE/BE | Conforme avec preuve | AGENTS, doctrine et contrats lus ; dépôts et dépendances inventoriés. | Instructions locales modifiées hors audit. |
| DEV02 | P0 | FE/BE | Conforme avec preuve | Routes, actions, RPC, crons, webhooks, workers et buckets inventoriés dans l'audit. | Configuration déployée non inventoriée. |
| DEV03 | P0 | FE/BE | Conforme avec preuve | Aucun contrôle désactivé ; migrations récentes durcissent RLS/grants. | Déploiement effectif non vérifié. |
| DEV04 | P0 | FE/BE | Conforme avec preuve | Valeurs de secrets jamais imprimées ; seulement noms/emplacements ; env ignorés. | Historique Git complet non scanné par outil dédié. |
| DEV05 | P1 | OPS | Non vérifié | Environnements Vercel/Supabase/Stripe non accessibles. | Mélange prod/preview possible. |
| DEV06 | P0 | BE | Non conforme | SEC-001 : URL client transformable en requête réseau worker ; contenu non exécuté comme shell mais frontière URL insuffisante. | SSRF worker. |
| DEV07 | P1 | OPS | Non vérifié | Contrats/rétention fournisseurs et données réellement envoyées non vérifiés. | Données client chez fournisseurs. |
| DEV08 | P0 | OPS | Conforme avec preuve | Aucun test intrusif tiers/production exécuté ; limites consignées. | Staging actif encore nécessaire. |
| DEV09 | P1 | FE/BE | Conforme avec preuve | Audit, registre, lots, critères et rollback demandé documentés. | Corrections non encore appliquées. |
| DEV10 | P0 | FE/BE | Conforme avec preuve | Défauts secrets/tenant/injection/paiement/coût priorisés. | SEC-001/002 ouverts. |

## Authentification

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| AUTH01 | P0 | FE | Conforme avec preuve | Supabase Auth ; aucun stockage de mot de passe/JWT maison. | Configuration fournisseur non vérifiée. |
| AUTH02 | P0 | FE | Conforme avec preuve | `auth.getUser()` dans proxy, `requireOrg`, admin et routes protégées. | Audience/issuer gérés par SDK, config effective non testée. |
| AUTH03 | P0 | OPS | Non vérifié | Aucune preuve MFA admin/client accessible. | Prise de compte admin. |
| AUTH04 | P0 | OPS | Non vérifié | Pas de limiteur applicatif login/signup ; réglages Supabase inconnus. | Brute force/automation. |
| AUTH05 | P1 | OPS | Non vérifié | Credential stuffing/challenge non documentés. | Attaques distribuées. |
| AUTH06 | P1 | FE | Conforme avec preuve | Login renvoie une erreur générique ; signup limite les détails. | Timings et recovery non testés. |
| AUTH07 | P0 | FE/OPS | Non vérifié | `safeRedirectTarget` protège le retour ; usage unique/TTL reset non testé. | Rejeu de reset. |
| AUTH08 | P1 | FE/OPS | Non vérifié | Réauthentification des opérations sensibles non démontrée. | Session volée. |
| AUTH09 | P0 | OPS | Non vérifié | Révocation/borne JWT Supabase non testée. | Token encore valide après révocation. |
| AUTH10 | P1 | FE | Non vérifié | Cookies gérés par `@supabase/ssr`; attributs runtime non inspectés. | XSS/session. |

## Autorisation et isolation

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| ACL01 | P0 | FE/BE | Non conforme | RLS/roles présents, mais `content_items` expose des champs serveur à UPDATE (SEC-001). | Transitions/worker manipulables. |
| ACL02 | P0 | FE | Conforme avec preuve | userId/org/role dérivés de `getUser()` + membership ; ids clients re-filtrés. | Matrice A/B runtime absente. |
| ACL03 | P0 | FE/BE | Non conforme | Refus tenant global, mais pas refus par défaut des colonnes/transitions de `content_items`. | Contournement métier. |
| ACL04 | P0 | FE/BE | Conforme avec preuve | Policies relient account/content/job à l'organisation ; AutoEdit revalide org avant service-role. | Test A/B requis. |
| ACL05 | P0 | BE | Non conforme | Grant UPDATE table-wide sur `content_items`; champs sensibles modifiables par Data API. | Mass assignment. |
| ACL06 | P0 | BE | Non vérifié | Politique après révocation pour jobs déjà réclamés non testée. | Ancienne tâche continue. |
| ACL07 | P1 | FE/BE | Non vérifié | Aucun flux d'invitation audité/trouvé dans le périmètre actif. | Escalade future. |
| ACL08 | P0 | FE/BE | Non vérifié | Migrations couvrent Data API/RPC/Storage, mais chemins directs non testés sur base déployée. | BOLA alternative. |
| ACL09 | P1 | FE | Conforme avec preuve | API privées `no-store`; AutoEdit URL signées fraîches et cache no-store. | CDN des vidéos publiques reste SEC-002. |

## Supabase et PostgreSQL

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| DB01 | P0 | BE | Non vérifié | Migrations activent RLS et révoquent de nombreux grants ; inventaire effectif impossible sans DB. | Table/migration oubliée. |
| DB02 | P0 | BE | Conforme avec preuve | Policies basées sur memberships/ownership, pas seulement `authenticated`. | Tests runtime manquants. |
| DB03 | P0 | BE | Non conforme | Plusieurs UPDATE historiques ont `USING` sans `WITH CHECK`; grant large `content_items`. | Réattribution/état nouveau. |
| DB04 | P0 | BE | Conforme avec preuve | Autorisation fondée sur tables membership, pas `user_metadata`. | Claims runtime non utilisés ici. |
| DB05 | P0 | BE | Non vérifié | Nombreuses fonctions SECURITY DEFINER durcies/revoquées, mais inventaire effectif et vues non testé. | RPC oubliée. |
| DB06 | P0 | FE/BE | Conforme avec preuve | Service role server-only, jamais NEXT_PUBLIC ; accès privilégiés explicités. | Surface de blast radius élevée. |
| DB07 | P1 | FE | Conforme avec preuve | Seules URL/anon key sont NEXT_PUBLIC ; contrôle réel dépend de RLS. | Test direct anon requis. |
| DB08 | P0 | BE | Conforme avec preuve | Colonnes org financières limitées ; ledger non insérable ; RPC atomiques server-only. | `completed_generations` reste modifiable via SEC-001. |
| DB09 | P0 | BE | Non vérifié | pgTAP présent mais non exécuté ; pas de comptes A/B réels. | Permissions effectives inconnues. |
| DB10 | P1 | OPS | Non vérifié | Connexions, rôles, backups/restauration non accessibles. | Continuité/accès DB. |

## Injections

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| INJ01 | P0 | FE/BE | Conforme avec preuve | SDK/RPC paramétrés ; aucune concaténation SQL observée. | Corpus runtime non exécuté. |
| INJ02 | P1 | FE/BE | Conforme avec preuve | Tri/colonnes dynamiques observés depuis constantes/allowlists. | Inventaire complet à maintenir. |
| INJ03 | P0 | FE/BE | Conforme avec preuve | Schémas/limites AutoEdit, script, quiz, sorties IA validés ; DB CHECK. | Profondeur JSON globale non bornée. |
| INJ04 | P0 | BE | Non conforme | Pas de shell utilisateur, mais URL/path réseau non suffisamment confinés (SEC-001). | SSRF/path média. |
| INJ05 | P0 | BE | Conforme avec preuve | FFmpeg reçoit des tableaux d'arguments ; pas de commande construite utilisateur. | Protocoles/décodeurs et ressources non confinés. |
| INJ06 | P0 | FE | Conforme avec preuve | React encode les sorties ; aucun `dangerouslySetInnerHTML` trouvé. | Markdown/SVG futurs. |
| INJ07 | P1 | FE/BE | Non vérifié | Plusieurs limites existent, mais ReDoS/complexité parseurs non testés. | DoS applicatif. |

## Navigateur et transport

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| WEB01 | P0 | FE/OPS | Conforme avec preuve | HSTS 2 ans + includeSubDomains/preload, CSP upgrade-insecure. | TLS production non sondé. |
| WEB02 | P0 | FE | Non vérifié | Server Actions/Supabase SSR apportent protections framework, mais test CSRF absent ; cron GET modifie l'état avec secret header. | CSRF/session ambient. |
| WEB03 | P1 | OPS | Non vérifié | CORS effectif Supabase/Vercel non audité. | Origines excessives. |
| WEB04 | P0 | FE | Conforme avec preuve | CSP nonce, strict-dynamic, frame-ancestors none, object-src none ; unsafe-eval dev seulement. | `unsafe-inline` styles accepté. |
| WEB05 | P1 | FE | Conforme avec preuve | nosniff, referrer policy, permissions policy, X-Frame-Options. | Headers runtime à sonder. |
| WEB06 | P1 | FE/OPS | Non vérifié | API no-store ; bundle/sourcemaps/previews/secrets prod non inspectés. | Fuite build/cache. |

## API et dépenses de génération

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| API01 | P0 | FE/BE | Non conforme | Actions protégées, mais Data API permet transitions directes `content_items`. | Contournement de file. |
| API02 | P0 | FE/BE | Conforme avec preuve | Limiteur Postgres partagé et verrou advisory. | Déploiement/runtime non testé. |
| API03 | P0 | FE/BE | Non conforme | Plusieurs limites existent, mais pas de limite IP fiable/concurrence globale fournisseur. | Abus multi-comptes/IP. |
| API04 | P1 | FE/OPS | Non vérifié | Aucun calcul IP audité ; limiteur actuel par user seulement. | Spoof/proxy. |
| API05 | P0 | BE | Conforme avec preuve | Réservation atomique avant coût, idempotence et remboursement ; tests SQL présents. | Tests concurrents non exécutés. |
| API06 | P0 | OPS/BE | Non vérifié | Quotas clients existent ; plafonds globaux fournisseur/projet et kill switch non démontrés. | Dépense agrégée. |
| API07 | P0 | FE/BE | Conforme avec preuve | Crédits idempotents par item/référence ; Stripe pack/plan par external_ref. | Idempotence générique des aides IA limitée. |
| API08 | P1 | FE/BE | Non conforme | Retries et jobs bornés par endroits ; pas de circuit breaker global démontré. | Accumulation/polling. |
| API09 | P0 | FE/BE | Conforme avec preuve | Limiteur/quota échoué => refus ; réservation refusée avant génération. | Data API SEC-001 à fermer. |
| API10 | P1 | OPS | Non vérifié | Trial présent ; anti-automatisation signup non démontrée. | Fermes de comptes. |
| API11 | P0 | FE/BE | Non conforme | Protections Server Actions contournables par UPDATE direct Supabase (SEC-001). | Chemin direct. |

## SSRF et ressources distantes

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| URL01 | P0 | BE | Non conforme | `_download` accepte l'URL de DB modifiable par client. | Proxy universel indirect. |
| URL02 | P0 | BE | Non conforme | Pas de canonicalisation/allowlist protocoles/ports dans trim. | Schémas/destinations hostiles. |
| URL03 | P0 | BE | Non conforme | Aucun blocage loopback/private/link-local/metadata IPv4/IPv6. | SSRF interne. |
| URL04 | P0 | BE | Non conforme | Redirections requests par défaut, DNS non revalidé. | Rebinding/redirection. |
| URL05 | P0 | OPS/BE | Non vérifié | Filtrage egress/isolation fetcher non démontré. | Impact SSRF maximal. |
| URL06 | P1 | BE | Non conforme | Timeout présent mais pas de taille/débit/décompression/redirection bornés. | DoS disque/mémoire. |

## Uploads et multimédia

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| FILE01 | P0 | BE | Non conforme | MIME/taille bucket et métadonnées bornées ; contenu réel/pixels/pistes non inspectés avant décodage. | Fichier polyglotte/bombe. |
| FILE02 | P1 | BE/OPS | Non vérifié | Quarantaine/antimalware/sandbox non démontrés. | Fichier hostile. |
| FILE03 | P0 | BE | Conforme avec preuve | Chemins serveur org/job, noms fixes, Path.resolve ; pas d'archive. | Sorties Generate anciennes non tenantées. |
| FILE04 | P0 | OPS | Non vérifié | UID, CPU/RAM/disque/temps/secrets worker non accessibles. | DoS/compromission. |
| FILE05 | P0 | BE/OPS | Non vérifié | Réseau décodeur non restreint ; FFmpeg protocol whitelist absente. | Lecture locale/réseau. |
| FILE06 | P1 | FE/BE | Conforme avec preuve | Upload AutoEdit limité aux MIME vidéo ; résultats mp4/jpeg. | Magic bytes toujours requis. |
| FILE07 | P0 | BE | Non conforme | AutoEdit privé et tenanté ; Generate `content-videos` public (SEC-002). | Fuite de vidéos. |
| FILE08 | P1 | FE/BE | Conforme avec preuve | AutoEdit URLs signées après contrôle d'org et no-store. | TTL/révocation runtime non testés. |
| FILE09 | P0 | FE/BE | Non conforme | Generate utilise URL publique permanente. | Export privé exposé. |

## IA et agents

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| AI01 | P0 | FE/BE | Conforme avec preuve | Entrées injectées comme données de prompt, pas comme permissions/outils. | Tests prompt adversariaux absents. |
| AI02 | P0 | FE/BE | Conforme avec preuve | Autorisation, quota, débit et publication sont déterministes serveur. | Data API transitions à fermer. |
| AI03 | P0 | BE | Conforme avec preuve | Aucun SQL/shell IA exécuté ; sorties passent par schémas. | Outils futurs à surveiller. |
| AI04 | P0 | BE | Conforme avec preuve | Historique/recommandations filtrés par account/tenant avant lecture. | Vector store non présent/audité. |
| AI05 | P1 | OPS/BE | Non vérifié | Clés non incluses, mais minimisation/rétention fournisseurs non vérifiées. | Confidentialité fournisseur. |
| AI06 | P0 | FE/BE | Conforme avec preuve | Tokens, retries, longueurs, quotas et coûts bornés dans le code observé. | Plafond global fournisseur absent. |
| AI07 | P0 | FE/BE | Conforme avec preuve | JSON/schémas IA validés avant DB/rendu. | Corpus hostile à ajouter. |
| AI08 | P0 | FE/BE | Conforme avec preuve | Publication nécessite action/cron autorisé et état connu ; modèle ne publie pas seul. | Auto-publish à tester A/B. |

## Paiements et crédits

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| PAY01 | P0 | FE/BE | Conforme avec preuve | Lookup keys/quantités serveur, owner requis, webhook/RPC accordent les crédits. | Catalogue Stripe runtime non vérifié. |
| PAY02 | P0 | FE | Conforme avec preuve | `constructEvent` avec corps brut et webhook secret. | Secret/destination Stripe runtime non vérifiés. |
| PAY03 | P0 | FE/BE | Non conforme | RPC crédits idempotentes ; pas de registre générique `event.id`. | Ordre/replay états abonnement. |
| PAY04 | P0 | FE/BE | Non vérifié | Aucun test accessible montant falsifié/replay/refund/dispute/downgrade complet. | Crédit incohérent. |
| PAY05 | P1 | FE | Conforme avec preuve | Checkout/Portal Stripe hébergés ; aucune donnée carte collectée. | Logs fournisseur non audités. |

## OAuth et services internes

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| OAUTH01 | P0 | FE | Conforme avec preuve | State HMAC avec nonce 256 bits, lié user/session par cookie HttpOnly, TTL dix minutes et consommé avant l'échange de token ; tests de régression. | PKCE et E2E fournisseur restent à vérifier. |
| OAUTH02 | P0 | FE | Conforme avec preuve | Callback revalide rôle, user et compte via RLS avant écriture service-role. | Test substitution runtime requis. |
| OAUTH03 | P0 | FE/OPS | Conforme avec preuve | AES-256-GCM, colonnes token retirées aux clients, server-only. | Gestion/rotation de clé non vérifiée. |
| INT01 | P0 | FE | Conforme avec preuve | Stripe signé ; crons Bearer secret en comparaison constante. | Replay cron non empêché, mais opérations conçues idempotentes en partie. |
| INT02 | P0 | FE/BE | Conforme avec preuve | Jobs/callbacks liés à ids connus et tenant ; fonctions financières server-only. | Matrice runtime absente. |
| INT03 | P1 | FE/BE | Non vérifié | Timeouts sur OAuth/transferts ; validation complète de toutes réponses fournisseur non prouvée. | Réponse externe malformée. |

## Infrastructure, dépendances et réponse

| ID | Priorité | Resp. | Statut | Preuve / justification | Risque résiduel |
|---|---:|---|---|---|---|
| OPS01 | P0 | OPS | Non vérifié | Noms de secrets inventoriés ; MFA/rotation/révocation non accessibles. | Clé compromise. |
| OPS02 | P0 | FE/BE | Conforme avec preuve | Secrets serveur hors NEXT_PUBLIC, env ignorés, service clients server-only. | Builds/historique exhaustif non scannés. |
| OPS03 | P1 | FE/BE | Non conforme | Lock npm et audit npm propre, mais versions Python non verrouillées/auditées. | Supply chain Python. |
| OPS04 | P1 | OPS | Non vérifié | Branch protection/reviews/token CI non accessibles. | Compromission CI. |
| OPS05 | P0 | FE/BE | Non vérifié | AutoEdit derrière flag ; endpoints debug/admin déployés non inventoriés runtime. | Surface oubliée. |
| OPS06 | P1 | OPS | Non vérifié | WAF/bot/DDoS non accessibles. | Abus volumétrique. |
| OPS07 | P0 | OPS | Non vérifié | Exposition DB/worker/queues non accessible. | Origine publique. |
| OPS08 | P0 | OPS | Non vérifié | Backups, chiffrement, restauration, RPO/RTO non accessibles. | Perte de données. |
| IR01 | P1 | FE/BE | Non conforme | Logs et audit admin/ledger présents ; corrélation/redaction systématique non démontrées. | Investigation incomplète. |
| IR02 | P1 | OPS | Non vérifié | Aucune règle d'alerte observée. | Incident silencieux. |
| IR03 | P1 | OPS | Non vérifié | Livraison/escalade non testées. | Dashboard non surveillé. |
| IR04 | P0 | OPS/BE | Non vérifié | Flags ponctuels ; kill switches globaux génération/publication/intégrations non démontrés. | Dépense/incident continue. |
| IR05 | P1 | OPS | Non vérifié | Aucun runbook accessible. | Réponse improvisée. |
| IR06 | P1 | OPS | Non vérifié | Aucun exercice restauration/clé compromise observé. | Reprise non fiable. |

## Matrice minimale avant lancement

| Test | Statut au 2026-10-03 | Critère bloquant |
|---|---|---|
| Appel anonyme action privée | Non vérifié runtime | Refus sans effet/coût. |
| A utilise ids de B | Non vérifié runtime | Refus DB, API, Storage et cache. |
| Membre révoqué / ancienne tâche | Non vérifié | Politique documentée et testée. |
| SQL/HTML hostile | Partiellement vérifié statiquement | Aucun changement de structure/XSS. |
| Login/reset répétés | Non vérifié | Limites multi-dimensionnelles. |
| Générations simultanées | Tests SQL présents, non exécutés | Aucun solde négatif/double débit. |
| Rejeu paiement/callback | Non conforme | OAuth one-shot corrigé ; registre événement Stripe encore requis. |
| URL vers réseau privé simulé | Non conforme | Aucune connexion interdite. |
| Fichier hostile/énorme | Non vérifié | Refus/isolement borné. |
| Prompt secret/outil interdit | Non vérifié actif | Aucune fuite/action. |
| Token expiré/révoqué | Non vérifié | Refus dans borne documentée. |
| Limiteur indisponible | Conforme avec preuve de code | Fail-closed avant coût. |
| Export/cache/lien privé | Non conforme Generate | Accès anonyme/B refusé. |
| Restauration/alerte | Non vérifié | Exercice avec preuve. |
