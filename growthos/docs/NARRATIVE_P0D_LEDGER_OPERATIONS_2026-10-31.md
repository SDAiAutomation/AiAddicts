# Contrôles opérationnels du journal de campagne (P0-D)

Ces contrôles sont **humains et documentaires** : aucune infrastructure n'est construite. Ils complètent les garanties du code (`p0d/ledger.py`) là où le code ne peut rien garantir : l'administration du répertoire et la discipline du propriétaire.

## 1. Une racine administrée unique

- Un seul répertoire de confiance (`ledger_root`) pour toutes les campagnes P0-D de la machine, **hors dépôt**, sur disque local (pas de partage réseau, pas de dossier synchronisé).
- Écriture réservée au compte qui exécute la campagne ; lecture limitée au propriétaire. Aucun autre processus ni compte n'y écrit.
- Le chemin est inscrit dans l'autorisation approuvée (`ledger_root`), sous forme absolue et canonique (le code refuse un alias). Il ne change pas pendant la durée d'une campagne.
- Le répertoire n'est jamais placé sous un dossier sauvegardé ou restauré automatiquement (voir §3).

## 2. Registre des `campaign_id`

Le code ne refuse un doublon que dans une même racine. Le propriétaire tient donc un registre **hors dépôt** (une simple feuille de calcul ou un fichier texte) avec une ligne par campagne :

| Champ | Contenu |
|---|---|
| `campaign_id` | unique pour toujours (jamais réutilisé, même après échec ; `LAB-…` pour le laboratoire) |
| `network_profile` | `production` ou `lab` |
| `ledger_root` | chemin canonique |
| `ledger_binding_sha256` | valeur retournée par `LedgerStore.initialize` |
| `authorization_sha256` | empreinte du fichier d'autorisation approuvé |
| dates | création, approbation, fin de fenêtre, clôture |
| état | `initialisée` / `en cours` / `bloquée` / `réconciliée` / `close` |
| observations | incidents, montants lus sur la facture du fournisseur |

Règles : on ajoute la ligne **avant** d'initialiser le journal ; un `campaign_id` perdu, réinitialisé ou abandonné reste dans le registre et ne sert plus ; deux autorisations ne partagent jamais le même identifiant.

## 3. Aucune restauration pendant une campagne

- Interdit : restaurer le répertoire ou le fichier du journal depuis une sauvegarde, un instantané de disque ou de VM, pendant qu'une campagne est ouverte ou **avant d'avoir terminé la réconciliation**. Une ancienne copie porte le bon nonce et n'est pas détectable : elle effacerait des tentatives déjà émises et donc payées.
- Les sauvegardes ne se font que **journal fermé** (campagne close ou bloquée, exécuteur arrêté) et ne servent qu'à l'archive.
- Si le journal est perdu ou corrompu : la campagne est **abandonnée**, pas reconstruite. Nouveau `campaign_id`, nouvelle autorisation, nouvelle approbation ; les dépenses de l'ancienne campagne se reconstituent à la main à partir des factures du fournisseur.
- Les instantanés de VM (laboratoire) se prennent et se restaurent **entre** campagnes, jamais pendant.

## 4. Réconciliation manuelle après incident

Un incident = campagne bloquée (`halted`) : coût inconnu, délai, réponse partielle, dépassement de la réservation, crash avec tentative `sending`, ou arrêt par l'opérateur. Procédure :

1. **Ne rien relancer.** L'exécuteur reste arrêté ; ne pas supprimer ni modifier le fichier du journal.
2. Fermer proprement l'exécuteur (`ledger.close()`), noter l'état dans le registre.
3. Lire le journal en lecture seule (`attempts()`, `events()`, `snapshot()`) : tentatives `unreconciled`, montant réservé, raison de l'arrêt.
4. Relever le coût **réel** de chaque tentative non réconciliée sur la facture ou le tableau de bord du fournisseur (jamais une estimation).
5. `reconcile(label, montant_réel, note)` pour chaque tentative, avec une note qui cite la source de la facture.
6. Décider : la campagne est-elle reprise ? Si oui, `clear_halt(note)` explicite (refusé tant qu'une tentative reste non résolue) puis **nouvelle fenêtre** (nouvelle ouverture, contrôle réseau vivant) ; sinon la clore dans le registre.
7. Consigner dans le registre le montant total réconcilié et l'écart avec l'estimation.

## 5. Ce que ces contrôles ne remplacent pas

Ils ne protègent pas d'un administrateur qui contourne la procédure, ni d'un disque perdu, ni d'un retour en arrière silencieux fait par un outil de sauvegarde que le propriétaire n'a pas désactivé sur ce répertoire. Ils rendent seulement ces risques explicites et vérifiables.
