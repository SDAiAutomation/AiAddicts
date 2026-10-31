# Exécuteur P0-D hors ligne : architecture, garanties et limites

Code : `engine/narrative_review/p0d/executor.py`, `authorization.py` (classe `Window`), `transport.py`, `tokenizer.py`, `egress.py`.
Tests : `test_p0d_executor.py`, `test_p0d_regressions.py`, `test_p0d_gates.py`. **Aucune connexion réelle** : l'émetteur du transport est toujours un objet factice injecté.

## Séquence (chaque appel)

`autorisation (temps)` → `empreintes` (autorisation, tarifs, attestation, enregistrement du tokenizer, profil) → `état réseau vivant « open »` → `tokenizer figé`
→ `budget` (maximum d'un appel : entrée + sortie + raisonnement distinct) → `réservation` → `vérification finale` (tout, à nouveau)
→ `transport` (créneau atomique, file d'envoi, contrôle complet, corps validé, **contrôle final**, émission) → `comptabilisation` → `réconciliation` (explicite).

## Ce qui est figé à l'ouverture de la fenêtre

| Élément | Comment |
|---|---|
| Autorisation | copie profonde immuable + empreinte ; comparée à chaque contrôle |
| Profil du modèle | objet + empreinte (paramètres, validateurs par nom qualifié) ; un autre objet, même identique, est refusé |
| Tarifs | `Prices` dérivés de l'autorisation, comparés à chaque contrôle |
| Tokenizer | **implémentation résolue** (instance), **fabrique du registre** (identité d'objet), **empreinte d'identité** (classe, état d'instance, code octet de `count`) ; l'enregistrement de validation est lié à cette empreinte |
| Attestation réseau | empreinte approuvée (état « rest ») ; chaque contrôle vivant doit être lié au même plan |
| Horloge | injectable (`Window(clock=...)`) pour les tests |

Tout écart ferme la fenêtre définitivement (`Window.close`) et l'exécuteur s'arrête (`WINDOW_CLOSED`).

## Contrôle réseau vivant obligatoire

`Window.open(..., egress_controller=...)` est obligatoire (paramètre sans valeur par défaut, `None` ou objet sans `check` refusés). Avant l'ouverture : état **« rest »** attesté, égal à l'attestation approuvée.
Ensuite, avant la réservation, après l'attente de la file, et au contrôle final : état **« open »** attesté, lié au même plan. Erreur, réponse d'un autre type, attestation non positive, mauvais état attendu,
plan différent : refus. Interface : `EgressController.check(expect) -> Attestation`.

- `FakeEgressController` : `kind = "simulated"`. **Jamais une preuve de coupure OS** ; le rapport de l'exécuteur le dit (`os_cutoff_proven = False`, `network_proof = "SIMULATED controller: NOT a proof…"`).
- `OsReadOnlyEgressController(plan, run_powershell)` : relit l'état réel via `verify_script` (lecture seule) par un lanceur **injecté**. Ne vaut que ce que valent ce lanceur et la machine. Même dans ce cas `os_cutoff_proven` reste faux : la coupure n'est que proposée.

## Libération d'une réservation

Le transport pose `SendTicket.emitted = True` juste avant l'appel de l'émetteur. Tant qu'il est faux, **il est prouvé** que rien n'est parti : la réservation est libérée (`Budget.release`, qui refuse une réservation réglée ou non réconciliée).
Dès qu'il est vrai (réponse, erreur HTTP, délai, redirection, `BaseException`) le montant est conservé `unreconciled`, l'exécuteur s'arrête, et aucun nouvel appel n'est possible avant `reconcile` explicite. Une tentative échouée arrête aussi le transport **atomiquement** avec l'enregistrement de la tentative : un envoi déjà en file ne peut pas partir après un échec.

## Garanties réelles (testées)

- Aucun envoi sans fenêtre ouverte, état réseau « open » attesté, empreintes et tokenizer inchangés au contrôle final.
- Un seul envoi par appel, aucun retry (`retries = 0`), plafond d'appels et plafond monétaire tenus sous concurrence.
- Arrêt global (`stop()` ou incident) : les appels en file sont refusés avant émission, leurs réservations libérées.
- Expiration, mutation du profil ou des tarifs, substitution du tokenizer, perte de l'attestation entre la réservation et l'envoi : refus, rien n'est émis, réservation libérée.

## Limites réelles

1. **Intervalle résiduel** : entre le contrôle final et l'appel de l'émetteur il reste quelques instructions. Une substitution à cet instant n'est pas détectable en Python pur. Seule la coupure réseau **au niveau de l'OS** (courtier bloqué par défaut, IP du fournisseur seules pendant la fenêtre) borne ce risque. Elle est proposée, pas appliquée, pas testée en conditions réelles.
2. L'empreinte du tokenizer ne couvre pas le code appelé par `count` (bibliothèques, globales). Un remplacement dans ce code n'est pas détecté.
3. Le coût est une **estimation** (jetons rapportés × tarifs approuvés), pas une facture.
4. ~~État budgétaire en mémoire~~ : remplacé par le journal durable (voir la mise à jour en bas de ce document).
5. Un fournisseur qui attend le plafond de raisonnement sous une autre forme qu'un entier simple demandera un profil adapté.
6. Les composantes facturables autres qu'entrée/sortie/raisonnement (jetons en cache, outils, images) ne sont pas modélisées : le corps est sur liste blanche et `tools` est protégé.

## Conditions avant un essai en environnement réseau isolé

1. Le propriétaire choisit le modèle, fournit ≥ 20 échantillons de comptage réels, enregistre son tokenizer et son profil de corps, produit l'enregistrement de validation, remplit l'autorisation (hors dépôt).
2. Copie dédiée de l'interpréteur pour le courtier ; plan de pare-feu renseigné ; `install_script` appliqué **par le propriétaire** sur une machine ou VM isolée ; `verify_script` relu ; empreinte « rest » reportée dans l'autorisation.
3. Sondes `probe_command` (cible TEST-NET-1) exécutées pour le harness et le courtier, résultats consignés ; tâche de refermeture testée à l'expiration **et** au redémarrage.
4. Contrôleur `os_readonly` branché sur un vrai lanceur PowerShell en lecture seule (non fait) et testé contre la machine isolée.
5. ~~Registre durable~~ : fait (`p0d/ledger.py`), à rejouer sur la machine isolée (scénario S9 du protocole).
6. Cible de test locale : un faux fournisseur sur un hôte du réseau isolé, jamais un fournisseur public ; vérifier que tout autre hôte est bien injoignable.
7. Validation des sources S01/S02 et recrutement de l'évaluation humaine (sans rapport avec le réseau, mais requis avant le pilote).
8. Nouvelle revue Codex de ce SHA, puis autorisation explicite du propriétaire pour tout appel payant (non demandée ici).

---
## Mise à jour : une seule tentative en vol, journal durable, tokenizer (contre-audit de b0eb195)

### Section critique de campagne
Toute la transaction d'un appel (décision sur la tentative précédente, contrôles, réservation durable, `sending`, émission, analyse, comptabilisation ou incident, décision de bloquer ou non la suivante) se déroule dans `CampaignLedger.critical_section()`.
Ce verrou est **propre à la campagne** (clé = fichier du journal) et partagé par toutes les instances d'exécuteur, de fenêtre et de transport du processus. Un verrou de fichier du système interdit un second **processus** propriétaire.
Le journal ajoute la garantie durable : au plus une tentative non résolue (`reserved`, `sending`, `unreconciled`), vérifiée dans la transaction qui crée la suivante.

### Journal financier durable (`p0d/ledger.py`)
SQLite local, `BEGIN IMMEDIATE`, `synchronous=FULL`, sans service. Une ligne par tentative : étiquette unique, numéro de séquence, **réservation maximale**, **état**, montant, note, horodatages ; journal d'événements en ajout seul (ni invite, ni secret).
`reserved` -> `sending` -> `settled` | `unreconciled` -> `reconciled`, ou `reserved` -> `released` (seule libération possible). Le marqueur `sending` est écrit **avant** l'appel de l'émetteur (échec d'écriture = rien n'est émis).
Redémarrage : `reserved` devient `released` (prouvé non envoyé) ; `sending` devient `unreconciled` et la campagne est **bloquée** jusqu'à `reconcile` puis `clear_halt` explicites. Plafonds d'appels et monétaire tenus durablement ; une étiquette n'est jamais réutilisée.

### Tokenizer et dépendances indirectes
L'empreinte couvre maintenant ce que `count` atteint : fonctions globales (suivies sur 4 niveaux), constantes de module, modules importés (version, empreinte du fichier, fonctions utilisées), version déclarée, état d'instance.
Deux niveaux : une empreinte **déterministe** (lie l'enregistrement de validation, valable d'un processus à l'autre) et une **épingle d'exécution** avec l'identité des objets du processus (un objet remplacé, même identique, est détecté). L'enregistrement est aussi lié à l'**environnement** (version et implémentation de Python, plateforme).
**Ce n'est pas une garantie d'intégrité absolue** : le code natif, les attributs de classes tierces et un code hostile du même processus échappent à ce contrôle. La solution proportionnée est : tokenizer **versionné**, dépendances **figées** (environnement virtuel verrouillé, hachages vérifiés à l'installation), et comptage dans un **environnement contrôlé** (idéalement le processus du courtier, un compte distinct).

### Garanties acquises (testées hors ligne)
- Une seule tentative en vol par campagne, entre threads et entre exécuteurs du même processus ; un second processus propriétaire est refusé.
- Réservation durable avant l'envoi ; aucune libération d'une tentative qui a atteint `sending` ; aucun double envoi ni double réservation après redémarrage ; plafonds durables.
- Après crash avant l'émission, après le marqueur, juste après l'émission, avant la comptabilisation, pendant la réconciliation : état cohérent, campagne bloquée si l'issue est incertaine, jamais de réenvoi.
- Remplacement d'une fonction globale, d'une constante de module ou d'une fonction de module utilisées par `count` après l'ouverture : plus aucun envoi.

### Garanties conditionnelles
- Elles supposent que tout envoi passe par ce module et que le fichier du journal n'est ni modifié ni supprimé hors module.
- La durabilité dépend de `fsync` du système de fichiers.
- Le blocage réseau n'est réel que si le propriétaire applique les règles proposées et que le pare-feu est actif (voir le protocole d'essai isolé).

### Limites de l'environnement Python
- Aucune empreinte Python n'est une barrière : du code du même processus peut modifier le vérificateur lui-même, `sys.modules`, ou utiliser le code natif.
- L'intervalle de quelques instructions entre le contrôle final / `sending` et l'appel de l'émetteur n'est pas fermable en Python pur.
- `Budget` en mémoire n'est qu'un miroir ; une instance n'y voit pas les écritures des autres : le journal décide.
- Le coût reste une estimation.

Protocole d'essai du pare-feu : `NARRATIVE_P0D_ISOLATED_NETWORK_TEST_PROTOCOL_2026-10-31.md`.

---
## Mise à jour : journal canonique, cycle de vie, règlement atomique (contre-audit de 530c02a)

### Journal canonique unique et racine de confiance
- **Un journal par campagne, chemin dérivé** : `<ledger_root>/campaigns/<sha256(campaign_id)[:32]>/ledger.sqlite`. `ledger_root` est un champ de l'autorisation approuvée ; l'exécuteur ne choisit jamais le chemin (`LedgerStore.open(auth)`). L'exécuteur refuse tout journal qui n'est pas lié à l'autorisation ou qui n'est pas au chemin canonique.
- **Lien durable** : le journal porte (`meta`) l'identifiant de campagne, l'empreinte du cœur de l'autorisation et un nonce aléatoire. L'autorisation porte `ledger_binding_sha256 = SHA-256(campagne, cœur, nonce)`. Le nonce n'existe que dans le journal d'origine : un journal absent, remplacé, copié, réinitialisé ou d'une autre autorisation ne peut pas reproduire l'empreinte. Chaque transaction et chaque lecture revérifient cette identité (remplacement en cours de route = échec sans envoi).
- **Racine de confiance** : (1) le répertoire administré `ledger_root` (écriture réservée au compte de la campagne) ; (2) l'autorisation approuvée, qui est l'ANCRE hors répertoire. Un marqueur voisin ne suffirait pas (supprimable et recréable avec le journal) : c'est pourquoi l'ancre est dans l'autorisation.
- **Création** : seulement `LedgerStore.initialize(cœur)`, étape du propriétaire AVANT l'approbation ; elle retourne la liaison à inscrire dans l'autorisation. `open` ne crée jamais rien (journal absent = refus, aucun fichier créé).
- **Politique de récupération** : un journal perdu, remplacé ou réinitialisé n'est PAS reconstruit. Il faut un nouvel identifiant de campagne et une nouvelle autorisation ; les dépenses de l'ancienne campagne se reconstituent à la main depuis les factures du fournisseur.
- **Chemins** : racine absolue, normalisée, existante et déjà canonique (ni lien symbolique, ni jonction, ni nom court, ni `..`, ni `.`, ni séparateur final) — l'alias est refusé, pas résolu ; fichier sans lien symbolique ni lien physique multiple ; clé de verrou = chemin réel normalisé (casse comprise).

### Limites de la racine de confiance
- Si le répertoire n'est pas administré (n'importe qui peut y écrire, supprimer ou restaurer), l'unicité ne peut pas être garantie ; le futur exécuteur impose ce répertoire par l'autorisation.
- **Retour en arrière** : une ancienne copie du journal d'origine porte le bon nonce et n'est pas détectable sans ancre externe. Mitigation : répertoire protégé, sauvegardes hors de portée de l'exécuteur, état final consigné par le propriétaire.
- Deux autorisations distinctes de même `campaign_id` dans des racines différentes sont deux campagnes aux yeux du système : l'unicité de l'identifiant entre autorisations relève du propriétaire (le magasin refuse un doublon dans une même racine).

### Cycle de vie
Après `close()` toute opération échoue (écritures, lectures, section critique). `close()` attend la fin d'une tentative en cours dans un autre thread (même verrou de campagne), refuse depuis l'intérieur d'une tentative, et n'expire pas silencieusement (`timeout` : erreur, journal toujours ouvert). Le verrou de fichier du système n'est relâché que par la dernière fermeture.

### Règlement et arrêt atomiques
`settle` inscrit le règlement ET la décision de blocage (dépassement de la réservation, ou raison d'arrêt de l'appelant) dans une seule transaction ; `mark_unreconciled` de même. Au redémarrage, tout règlement en dépassement non bloqué est bloqué (filet). Les pannes ont été testées de chaque côté du commit de chaque transition.

### Profil réseau de laboratoire
`network_profile` ∈ {`production`, `lab`} fait partie de l'autorisation, du plan et de l'attestation. Un profil `lab` exige : `campaign_id` commençant par `LAB-`, un hôte réservé `*.invalid` (jamais résoluble sur Internet), des IP privées dans un `lab_cidr` privé (≤ 256 adresses), et l'ouverture explicite `Window.open(allow_lab=True)`. Une autorisation de production refuse tout marqueur de laboratoire, un plan de production refuse les IP privées, et le profil attesté doit égaler celui de l'autorisation à l'ouverture et à chaque contrôle (sinon la fenêtre se ferme). Les règles et la propriété « bloqué par défaut » sont identiques ; rien n'est relâché.

