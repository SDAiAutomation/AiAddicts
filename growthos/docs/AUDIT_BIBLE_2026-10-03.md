# Audit Faceloop selon la bible du 3 octobre 2026

Source : `Bible_Faceloop.md` (version du 3 octobre 2026), confrontée à AGENTS.md, PRODUCT_DOCTRINE.md, README.md, PRODUCT_ARCHITECTURE.md, aux 56 migrations, à `worker.py`, `engine/assembler.py` et au workflow GitHub Actions. Le web (`growthos-web`, propriété de Codex) n'a été relevé qu'en surface.

**Vérifié le 2026-10-03 :**
- Les 783 tests du moteur passent (Python, sans appel réseau ni ffmpeg).
- Le dépôt moteur est propre (`growthos/mvp`).
- Le web était sur la branche `fix/quiz-preview-centred`, pas sur `master`.

**Non vérifié :** tout ce qui touche à la production réelle (base distante, Vercel, comptes de publication).

## 1. Cartographie

| Couche | Existant | Preuve |
|---|---|---|
| Interface | Next.js sur Vercel. Pages : création, bibliothèque, séries, comptes, analytics, quiz, AutoEdit, admin. | `growthos-web/src/app/(app)/*` |
| Moteur | Python : script, voix, images, rendu ffmpeg, sous-titres, contrôles qualité, originalité, rétention. | `engine/*.py` (≈10 000 lignes) |
| Traitement long | Workflow GitHub Actions toutes les 10 min, timeout 12 min, file via `content_items.status`. | `.github/workflows/growthos-worker.yml`, `worker.py` |
| Stockage | Supabase : base, Storage (`content-videos`), RLS durcie (migration du 2 octobre). | `supabase/migrations/` |
| Crédits | Réservation au début, remboursement si échec. Ledger `credits_ledger`, plafonds de plan, quota d'appels IA, pack de crédits, ajout manuel par un admin tracé. | `20260915120000_atomic_credit_reservation.sql`, `20261002190000_admin_credit_grants.sql` |
| Publication | TikTok (statut de publication suivi), YouTube Shorts, `content_publication_jobs` unique par `(content_item, plateforme)`. | migrations 0917 et 1002 |

## 2. Capacités vs bible

| Exigence de la bible | État | Constat |
|---|---|---|
| Crédits réservés avant l'appel payant, sans double débit | **Existe** | Réservation avec verrou sur l'organisation, rejouable sans redébiter (`reserve_generation_credit`). |
| Remboursement en cas d'échec | **Existe** | Remboursement si la génération ou l'envoi échoue. Un worker tué par le timeout est rattrapé par `reclaim_stale_generating_items` (remise en file, sans remboursement ; l'idempotence évite un second débit). |
| Registre avec consommations et libérations par opération | **Partiel** | Ledger lié au `content_item`, pas à un identifiant d'opération. Ne couvre pas les corrections (inexistantes). |
| Rejeu, crash, timeout après facturation fournisseur, échec partiel | **Non vérifié** | Tests unitaires de crédits (`test_repo_credits.py`), aucun test de bout en bout de ces scénarios. |
| Coût par vidéo | **Partiel** | `generation_cost_report` couvre images, voix, script, originalité ; vues SQL. Manquent : échecs, rendu, stockage, transfert. Seule mesure connue (mémoire) : ≈ 0,34 à 0,37 $/vidéo, ponctuelle. |
| Correction locale avec réutilisation des ressources | **Absent** | Voir point critique. Seul le rognage début/fin est local (`trim.py`, `video-editor.tsx`). |
| Versions immuables et retour arrière | **Absent** | Une régénération écrase la vidéo. Le rognage garde une archive `original`, rien de plus. |
| Publication liée à la version exacte validée | **Absent** | La publication cible le `content_item`, pas un fichier versionné. |
| Mémoire de série (personnages, faits canon, intrigues) | **Partiel** | `series` : prémisse, style, voix, langue. `image_character_bible.py` est conditionnel et par script. Ni fiche personnage persistante, ni canon, ni approuvé / proposé / rejeté. |
| Anti-répétition et originalité | **Existe** | `originality.py`, activé en production le 24/09 (selon la mémoire). Premiers rapports réels à examiner. |
| Moteur de rétention et intégrité | **Existe** | `retention.py`, `integrity.py`, `RETENTION_ENGINE.md`. |
| Boucle d'apprentissage | **Existe** | `learning.py`, suivi des recommandations. Quasi aucune donnée réelle (1 seule vidéo `motion_graphics` publiée sur 47). |
| Estimation du coût avant action payante (côté client) | **Non vérifié** | Côté web, à confirmer avec Codex. |
| Export MP4, script, sous-titres | **Partiel** | MP4 téléchargeable. `.srt` et script produits côté serveur mais non exposés comme export. |
| Instrumentation (activation, D7, temps jusqu'à la première vidéo satisfaisante) | **Absent** | Aucune table d'événements produit trouvée. |
| Benchmark de 30 à 50 briefs | **Partiel** | Benchmark de rétention (`content/scripts/retention/BENCHMARK.md`), pas de bout en bout. |

### Point critique : une correction coûte une régénération complète

- Le cache de rendu est indexé par une empreinte du script, de la voix, des réglages et du code (`generation_cache.py`). Modifier un mot change l'empreinte.
- Le worker tourne sur un runner GitHub éphémère, sans cache ni artefact conservé entre les passages : images, voix et clips déjà payés sont perdus.
- Aucun mécanisme de régénération partielle.

Corriger une petite erreur coûte donc le temps (10 à 20 min) et la dépense d'une vidéo neuve. Cela contredit le premier principe non négociable de la bible.

### Risque de facturation, à confirmer

D'après le SQL, si la réservation d'un `content_item` est déjà nette (-1), `reserve_generation_credit` répond « vrai » sans débiter. Une régénération complète du même élément serait gratuite pour le client alors qu'elle coûte ≈ 0,34 $. Non vérifié : le web remet-il le ledger à zéro ou crée-t-il un nouvel élément ? À tester en premier ; la politique client reste à décider.

## 3. Difficultés du parcours réel

1. **Génération** : latence 10 à 20 min ; planificateur toutes les 10 min ; limite de 12 min pouvant interrompre une vidéo longue.
2. **Correction** : régénération complète, ou rognage seulement.
3. **Récupération** : MP4 seul, pas de pack script / sous-titres / ressources.
4. **Retour pour une nouvelle création** : boucle d'apprentissage sans données, mémoire de série mince.

## 4. Coûts

- **Connus** : images, voix, script, originalité (estimations par génération, `engine/assembler.py` ; vues `generation_cost_by_org_month`, `generation_cost_weekly`).
- **Inconnus** : coût des échecs et reprises, stockage et transfert Supabase (plan Pro depuis le 21/09), coût réel facturé vs estimé. Le rendu est gratuit (GitHub public).
- **Méthode proposée** : événement `video_satisfying` (export, publication ou déclaration du créateur) ; coût total des essais ÷ vidéos satisfaisantes ; médiane et P90 ; comptes internes séparés des clients.

## 5. Écarts bible / existant

| Prio | Écart |
|---|---|
| **P0** | Correction locale et manifeste d'actifs réutilisables (absent) |
| **P0** | Versions immuables et publication liée à une version (absent) |
| **P0** | Politique et tests de régénération, rejeu, crash, timeout après facturation (non vérifié, risque de marge) |
| P0 | Export complet MP4 + script + sous-titres (partiel) |
| P1 | Mémoire de série : fiches personnages, canon approuvé / proposé / rejeté (partiel) |
| P1 | Estimation du coût visible avant l'action (non vérifié, côté Codex) |
| P2 | Instrumentation des indicateurs produit et benchmark 30 à 50 briefs (absent) |

**Conflits à trancher :**
- AGENTS.md priorise Story Engine 2.0, anti-répétition et cohérence visuelle (largement livrés) ; la bible priorise fiabilité et correction. Proposition : suivre la bible.
- La doctrine garde AutoEdit comme second moteur, la bible le met en P3.
- AGENTS.md confie Quiz à Codex, la bible le met en P2.

## 6. Lots proposés

| Lot | Contenu | Dépend de | Effort | Validation |
|---|---|---|---|---|
| **L0** Garde-fous de crédit | Test « régénération du même élément ». Décision de politique client. Tests de rejeu, crash worker, échec partiel. Ledger rattaché à une opération. | Décision métier | 2 à 4 j | Aucun double débit, aucune régénération gratuite non voulue. |
| **L1** Manifeste d'actifs et correction locale | Table des actifs (type, scène, hash d'entrée, chemin Storage, coût, statut). Régénération d'une image, d'une voix ou des sous-titres, puis rendu en réutilisant les actifs valides. | L0 | 2 à 3 sem. | Corriger une scène ne rappelle que l'image de cette scène, coût et durée mesurés. |
| **L2** Versions et export | Versions immuables, retour arrière, publication liée à la version, export MP4 + `.srt` + script. | L1 | 1 à 2 sem. | Une publication pointe vers un fichier identifiable. |
| **L3** Contrat web de correction | Écrans de correction, estimation du coût, états lisibles. | L1 (contrat API) | 1 à 2 sem. (Codex) | Parcours testé sur mobile et iPhone. |
| **L4** Mémoire de série minimale | Fiches personnages persistantes, faits canon approuvés / proposés, usage dans l'anti-répétition. | L2 | 2 à 3 sem. | Scénario « secret de l'épisode 4 » de la bible. |
| **L5** Instrumentation et benchmark | Événements produit, cohortes, 30 à 50 briefs. | Indépendant | 1 à 2 sem. | Le coût par vidéo satisfaisante se calcule. |

Efforts = intervalles à recalibrer. Le coût de la persistance Storage n'est pas mesuré.

## 7. Lot recommandé : L0 puis L1

**Résultat client :** corriger une scène, une phrase ou une prononciation sans attendre une vidéo entière ni repayer ce qui était déjà bon.

**Pourquoi :** douleur la plus fréquente et visible ; réduit aussi les coûts ; alimente L2, L3, L4 ; fondation neutre vis-à-vis des futurs modèles (manifeste d'actifs, versions).

**Critère de réussite** (sur une vidéo réelle, avec accord pour la dépense) :
1. Une correction d'image seule rappelle un seul appel image (rapport de coût).
2. Coût et durée inférieurs à 20 % d'une régénération complète.
3. Aucun double débit sur double clic ou requête rejouée.

**Limites :** aucune génération réelle ni modification de production sans accord ; rien déclaré « prêt production » sur la seule base de tests.

## Décisions à prendre (fondateur)

1. Politique client pour une régénération : gratuite, payante, ou une retouche gratuite puis payante ?
2. Confirmer l'ordre : bible (fiabilité d'abord) plutôt que l'ordre d'AGENTS.md.
3. Autorisation de créer la table des actifs et d'appliquer la migration en production, quand le lot sera prêt.

## Validation réelle des lots L0 et L1 (2026-10-03)

Vidéo de test « L'enfant bénie » (3 blocs, Dogfooding, élément `8fb753ce`), créée et régénérée trois fois par l'utilisateur dans l'application. Relevé en base (ledger, `content_assets`, `generation_cost_report`).

| Run | Ce qui a changé | Actifs régénérés | Crédit |
|---|---|---|---|
| A | première génération | 3 voix + 3 images | -1 (run 1) |
| B | texte du bloc 2 | 1 voix + 1 image (le bloc n'a pas de champ `visual` : son image dérive du texte) ; 2 voix + 2 images réutilisées | 0 (retouche gratuite) |
| C | visuel du bloc 3 | 3 images ; 3 voix réutilisées | -1 (run 3) |

Constats :
- **L0 validé en réel** : le run 2 est gratuit, le run 3 débite, `completed_generations` = 3.
- **L1 validé en réel** : la persistance entre runs (runner éphémère) fonctionne ; au run B, seuls les actifs du bloc modifié sont repayés (≈ 0,017 $ contre ≈ 0,049 $ pour tout régénérer ; plancher mécanique de 1/3 sur une vidéo de 3 blocs, il baisse avec le nombre de blocs).
- **Run C : les 3 images ont été régénérées**, pas seulement celle du bloc 3. Le coût par image est passé de ≈ 0,0123 à ≈ 0,0132 $ (≈ +190 tokens de prompt), ce qui correspond à une fiche personnage ajoutée à tous les prompts entre B et C. La clé couvre le prompt final : ce comportement est cohérent avec la règle (cohérence du personnage), mais il est invisible pour le créateur. À traiter en L3 : prévenir avant la génération du nombre d'actifs qui seront régénérés et pourquoi. Cause exacte du changement de fiche non établie (extraction automatique à la mise en file ou modification manuelle).
- **Non mis en cache** : le contrôle d'originalité (appel LLM ≈ 0,008 $) est refait à chaque run, soit une part notable du coût d'une retouche sur une vidéo courte.
- **Stockage** : ≈ 157 Ko par image, ≈ 27 Ko par voix, soit environ 2 Mo par vidéo de 12 scènes : négligeable.
- Le rapport de coût ne conserve que le dernier run ; les runs A et B ont été reconstitués depuis les horodatages du manifeste.
