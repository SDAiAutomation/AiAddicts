# Protocole d'essai du pare-feu en réseau isolé (faux fournisseur joignable)

**Statut : protocole RÉDIGÉ, rien n'a été exécuté, aucune règle appliquée.** Il est destiné au propriétaire, sur une machine virtuelle isolée. Aucun appel à un vrai fournisseur, aucun trafic vers Internet, aucune dépense.
Principe : **on ne relâche aucune règle de sécurité pour faciliter l'essai.** Les mêmes scripts (`install_script`, `open_script`, `close_script`, `verify_script`, `profiles_script`, `probe_command`) et le même plan que ceux d'une vraie campagne sont utilisés ; seul le « fournisseur » est un faux serveur sur un réseau virtuel sans sortie.

## 1. Architecture

```
            (aucune carte, aucun NAT, aucune passerelle vers l'hôte ni vers Internet)
   ┌───────────────────── commutateur virtuel PRIVÉ « p0d-lab » ─────────────────────┐
   │                                                                                 │
 VM-A « campagne »                       VM-B « faux fournisseur »                    │
 <P>.10/24                               <P>.20/24  (+ alias <P>.30/24 « leurre »)     │
 - copie H de l'interpréteur (harness)   - serveur TLS :443 (certificat auto-signé,    │
 - copie B de l'interpréteur (courtier)    nom = provider_host du plan)                │
 - copie T de l'interpréteur (TÉMOIN)    - serveur TLS :8443 sur <P>.20 (témoin port)   │
 - exécuteur hors ligne + journal        - serveur TLS :443 sur <P>.30 (témoin IP)      │
                                         - écho UDP :443 sur <P>.20 (témoin UDP)        │
```

- **Hyperviseur** : commutateur de type *Privé* (Hyper-V) ou réseau *interne sans NAT* ; aucune carte virtuelle de l'hôte dans ce commutateur ; services d'intégration « synchronisation de l'heure » désactivés pour VM-A (l'heure est pilotée à la main pour tester l'expiration).
- **Adresses (profil laboratoire)** : `<P>` est un réseau PRIVÉ (RFC 1918) de 256 adresses au plus, par exemple `10.77.0.0/24`, qui n'existe que dans le commutateur privé. Le profil `lab` du plan (`profile="lab"`, `lab_cidr="10.77.0.0/24"`) n'accepte que ces adresses privées ; le profil `production` continue de n'accepter que des IP publiques. **Aucune règle de la production n'est relâchée** : les adresses privées ne sont acceptées que si le plan, l'autorisation ET l'attestation portent le profil `lab`.
- **Adresses autorisées dans le plan** : `provider_ips = (<P>.20,)` uniquement. `<P>.30` (leurre) et `<P>.10` (VM-A) n'y figurent pas.
- **Programmes** : `harness_program` = copie H, `broker_program` = copie B (copie dédiée, chemin distinct), copie T = programme **témoin** sans aucune règle.
- **Instantané** de VM-A avant le test et après chaque scénario (retour arrière sans conséquence). Les scripts d'application sont lancés **par le propriétaire**, en administrateur, **dans la VM**, jamais sur la machine hôte.

## 1 bis. Profil laboratoire, explicitement distinct de la production

| Élément | Production | Laboratoire |
|---|---|---|
| `network_profile` (autorisation) | `production` | `lab` |
| Identifiant de campagne | ne commence jamais par `LAB-` | commence par `LAB-` |
| Hôte du fournisseur | jamais en `.invalid` | `*.invalid` (nom réservé, jamais résoluble sur Internet ; la connexion se fait par IP épinglée) |
| IP du plan | publiques (globales) | privées, dans `lab_cidr` (≤ 256 adresses), ni réseau ni diffusion |
| Ouverture de la fenêtre | normale | `Window.open(allow_lab=True)` explicite |
| Attestation | profil `production` | profil `lab` ; l'empreinte du plan inclut le profil |
| Contrôle à chaque envoi | profil attesté = profil de l'autorisation | idem ; tout changement ferme la fenêtre |

Refus testés : autorisation de production avec marqueur de laboratoire ; autorisation `lab` sans marqueur ; plan `lab` avec IP publique ou hors du réseau privé ; plan de production avec IP privée ou `lab_cidr` ; plan `lab` servant une autorisation de production (et l'inverse) ; attestation `lab` pour une autorisation de production, même avec `allow_lab=True`.
Le journal de campagne du laboratoire est un journal canonique ordinaire (`LedgerStore`), dans une racine de confiance de la VM, avec une campagne `LAB-…` jetable.

## 2. Témoins

Chaque résultat négatif n'a de valeur que si le témoin correspondant prouve que le réseau fonctionne.

| Code | Témoin | Attendu |
|---|---|---|
| T0 | Isolement : depuis VM-A, joindre un hôte Internet par IP et par nom (avant toute règle) | **échec** (sinon, arrêter : le commutateur n'est pas isolé) |
| P0 | Positif de contrôle : copie **T** (aucune règle) joint `<P>.20:443`, `<P>.20:8443`, `<P>.30:443` et l'écho UDP | **succès** partout (le réseau virtuel fonctionne) |
| P1 | Positif d'ouverture : copie **B** joint `<P>.20:443` en TLS, avec le nom du plan, **pendant la fenêtre** | **succès** |
| N1 | Négatif IP : copie B joint `<P>.30:443` | échec, repos et ouverture |
| N2 | Négatif port : copie B joint `<P>.20:8443` | échec, repos et ouverture |
| N3 | Négatif UDP : copie B envoie à `<P>.20:443/udp` | échec, repos et ouverture |
| N4 | Négatif harness : copie H joint `<P>.20:443`, `<P>.30:443`, localhost non filtré (note : la boucle locale n'est pas filtrée par Windows) | échec vers toute adresse distante, tous états |
| N5 | Négatif repos : copie B joint `<P>.20:443` **hors fenêtre** | échec |
| N6 | `probe_command` (TEST-NET-1) pour H et B | échec / injoignable |

## 3. Scénarios

Avant chaque scénario : `verify_script` + `profiles_script` (lecture seule), puis attestation (`attest`, `check_profiles`).

1. **S0 — Isolement** : T0, P0 sans aucune règle.
2. **S1 — Installation (état de repos)** : le propriétaire exécute `install_script`. Relire l'état ; **l'attestation « rest » doit être positive** ; reporter son empreinte dans l'autorisation d'essai. Jouer N1–N6 et N5 : tout échoue pour H et B ; P0 réussit toujours pour T.
3. **S2 — Ouverture** : exécuter `open_script` (qui vérifie les règles permanentes, l'horloge, enregistre la tâche de refermeture, retire le verrou). Attestation « open » positive. Jouer P1 (réussit) et N1–N4 (échouent). Lancer l'exécuteur hors ligne **avec un faux fournisseur réel sur `<P>.20`** : un appel complet, journal à jour.
4. **S3 — Fermeture manuelle** : `close_script`. Attestation « rest » ; N5 échoue ; l'exécuteur refuse (contrôle vivant).
5. **S4 — Expiration** : ouvrir la fenêtre avec une durée courte (ex. 10 min) ; avancer l'horloge de VM-A au-delà de `window_end` **sans intervention** ; la tâche `RECLOSE` remet le verrou. Attestation « rest » ; N5 échoue ; l'exécuteur refuse (fenêtre expirée **et** état « rest »).
6. **S5 — Redémarrage fenêtre ouverte** : ouvrir, redémarrer VM-A **avant** toute connexion de session ; la tâche `AtStartup` remet le verrou ; relire l'état au démarrage : attestation « rest », N5 échoue.
7. **S6 — Redémarrage au repos** : les règles persistantes sont toujours là ; attestation « rest ».
8. **S7 — Ouverture défectueuse** : désactiver une règle permanente (p. ex. `BROKER-BLOCK-OUTSIDE`) puis `open_script` : il doit **échouer avant** de retirer le verrou ; P1 échoue.
9. **S8 — Altération** : supprimer le verrou à la main hors fenêtre, ajouter une règle d'**autorisation** pour B, passer un profil sur « Désactivé » (`profiles_script`), arrêter le service pare-feu : chaque cas doit rendre l'attestation **négative** et faire **refuser** l'exécuteur. Si l'un d'eux ne l'est pas, c'est un défaut à corriger avant toute suite.
10. **S9 — Crash de l'exécuteur** : tuer le processus (arrêt brutal) pendant un appel contre le faux fournisseur : au redémarrage le journal bloque la campagne (tentative `sending` -> non réconciliée) ; aucun double envoi.

11. **S10 — Étanchéité des profils** : présenter à l'exécuteur (a) une autorisation `production` avec le contrôleur `os_readonly` branché sur le plan `lab` ; (b) une autorisation `lab` avec un plan de production ; (c) une autorisation `lab` sans `allow_lab`. Les trois doivent être refusées **avant** toute connexion.
12. **S11 — Journal canonique** : supprimer, remplacer par une copie, ou réinitialiser le journal de la campagne `LAB-…` entre deux exécutions ; l'exécuteur doit refuser sans aucun envoi vers le faux fournisseur (compteur de connexions de VM-B inchangé).

## 4. Critères de réussite et d'arrêt

- Réussite = tous les attendus ci-dessus **et** chaque négatif accompagné de son positif de contrôle (P0).
- **Arrêt immédiat** si T0 réussit (isolement rompu), si un négatif réussit, si une attestation positive est donnée à un état altéré, ou si la VM-A a un accès à autre chose que le commutateur privé. Restaurer l'instantané, ne pas poursuivre.
- Les résultats (sorties de `verify_script`, `profiles_script`, des sondes, empreintes d'attestation, extraits du journal) sont consignés **hors dépôt**.

## 5. Ce que ce protocole ne prouve pas

Il ne prouve pas la coupure sur la machine de production (autre pare-feu, autre pilote, pare-feu tiers, VPN), ni l'absence d'un chemin réseau hors de Windows Filtering Platform (pilote, service SYSTEM). Il ne valide ni le comportement d'un vrai fournisseur ni la facturation.
