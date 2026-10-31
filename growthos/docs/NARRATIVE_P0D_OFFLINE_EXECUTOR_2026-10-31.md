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
4. **L'état budgétaire est en mémoire** : un plantage du processus perd réservations et montants non réconciliés. Un registre durable est nécessaire avant un essai réel.
5. Un fournisseur qui attend le plafond de raisonnement sous une autre forme qu'un entier simple demandera un profil adapté.
6. Les composantes facturables autres qu'entrée/sortie/raisonnement (jetons en cache, outils, images) ne sont pas modélisées : le corps est sur liste blanche et `tools` est protégé.

## Conditions avant un essai en environnement réseau isolé

1. Le propriétaire choisit le modèle, fournit ≥ 20 échantillons de comptage réels, enregistre son tokenizer et son profil de corps, produit l'enregistrement de validation, remplit l'autorisation (hors dépôt).
2. Copie dédiée de l'interpréteur pour le courtier ; plan de pare-feu renseigné ; `install_script` appliqué **par le propriétaire** sur une machine ou VM isolée ; `verify_script` relu ; empreinte « rest » reportée dans l'autorisation.
3. Sondes `probe_command` (cible TEST-NET-1) exécutées pour le harness et le courtier, résultats consignés ; tâche de refermeture testée à l'expiration **et** au redémarrage.
4. Contrôleur `os_readonly` branché sur un vrai lanceur PowerShell en lecture seule (non fait) et testé contre la machine isolée.
5. Registre durable des réservations et des montants non réconciliés (non fait).
6. Cible de test locale : un faux fournisseur sur un hôte du réseau isolé, jamais un fournisseur public ; vérifier que tout autre hôte est bien injoignable.
7. Validation des sources S01/S02 et recrutement de l'évaluation humaine (sans rapport avec le réseau, mais requis avant le pilote).
8. Nouvelle revue Codex de ce SHA, puis autorisation explicite du propriétaire pour tout appel payant (non demandée ici).
