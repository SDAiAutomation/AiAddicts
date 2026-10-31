# Conception : coupure réseau OS et transport instrumenté (P0-D)

Statut : **proposition** + briques testées hors ligne. Aucune règle de pare-feu n'a été appliquée, aucun fournisseur n'a été contacté.

## Pourquoi le crochet CPython ne suffit pas

Le crochet d'audit bloque les appels Python (`socket`, sous-processus, chargement natif) pendant une campagne hors ligne. Il n'arrête pas une extension native qui ouvre ses propres connexions, ni un code qui modifie les globales du module. Pour un vrai fournisseur, il faut une coupure que **le système d'exploitation** impose à un processus, vérifiable sans exécuter ce code.

## Architecture à deux processus

```
 processus de CAMPAGNE (interpréteur « harness »)         COURTIER de transport (copie dédiée de l'interpréteur)
   - prompts, budget, journal, critique                    - Window (autorisation) + MeteredTransport + HttpClientSender
   - pare-feu : TOUT sortant distant BLOQUÉ en permanence  - pare-feu : sortant bloqué sauf IP du fournisseur, TCP 443
   - ne joint que le courtier, via la boucle locale        - IP pinée (aucun DNS), certificat vérifié pour le NOM autorisé
```

- La boucle locale n'est pas filtrée par le pare-feu Windows : le harness peut joindre le courtier, et **rien d'autre**.
- Un **blocage l'emporte sur une autorisation** dans le pare-feu Windows. « Seulement ces adresses » s'exprime donc par le **complément** : des règles de blocage couvrant tout l'espace d'adresses sauf les IP du fournisseur (IPv4 et IPv6), un blocage de tous les ports sauf 443 vers ces IP, et un blocage UDP total. Aucune règle d'autorisation n'est créée. `complement_ranges` est testée : couverture complète, sans trou ni chevauchement.
- Le courtier est une **copie de l'interpréteur à un chemin dédié** : une règle par programme ne doit viser que lui.

## Fenêtre : comment les appels sont autorisés uniquement pendant la campagne

1. Le blocage du harness est **permanent**. Hors fenêtre, le courtier n'a aucune règle d'accès : il n'a pas non plus de destination.
2. Le propriétaire relève les IP du fournisseur et exécute `open_script` (administrateur). Il crée les règles du courtier et une **tâche planifiée d'expiration** qui les supprime à la fin de la fenêtre.
3. Le propriétaire exécute `verify_script` (lecture seule) puis `attest` : l'**empreinte d'attestation** lie le plan et l'état observé des règles. Il la reporte dans `authorization.json` (champ `egress_attestation_sha256`) et approuve l'autorisation (hôte unique, plafond, tarif daté, fenêtre <= 48 h).
4. Au démarrage de la campagne : `Window.open` exige l'autorisation valide **et** que l'attestation recalculée (`live_attestation`) soit celle approuvée. Chaque envoi appelle `Window.check` : expiré, fermé ou non ouvert = aucun envoi.
5. Après la campagne : `close_script` supprime les règles du courtier ; `Window.close` est définitif.

## Vérification indépendante de CPython

- `verify_script` lit l'état **réel** du pare-feu (cmdlets de lecture seule, testé : aucun `New-`, `Remove-`, `Set-`, `netsh`...). Il a été exécuté sur cette machine : 15 s, code 0, sortie `[]` pour un plan inconnu.
- `attest` refuse : règle absente, désactivée ou modifiée, trou ou chevauchement dans la couverture, règle supplémentaire portant le préfixe de la campagne, règle d'**autorisation** active visant l'un des deux programmes.
- `probe_command` : sonde externe à lancer par le propriétaire **après** application des règles. Elle tente une connexion vers `192.0.2.1` (TEST-NET-1, adresse de documentation : aucun serveur ne peut répondre) depuis chacun des deux programmes. Avec les règles, rien ne sort de la machine.

## Transport instrumenté

- **Une tentative par envoi**, sans boucle. `HttpClientSender` : `http.client`, sans reprise, sans suivi de redirection, sans proxy d'environnement ; 429, 5xx, 3xx, délai dépassé = échec visible.
- **Tentatives réelles mesurées** par le transport (connexions `socket.connect` ouvertes pendant l'appel), indépendamment de ce que l'émetteur déclare : plus d'une connexion = reprise cachée ou redirection ; le transport se **déclenche** et refuse tout envoi suivant.
- **Jetons et coûts renvoyés** par le fournisseur (`usage`), jamais calculés par le transport ; coût « observé » seulement s'il est renvoyé, sinon `None`. Les jetons de raisonnement sont reportés à part pour audit.
- **Garde d'entrée** : tokenizer résolu par l'autorisation (`TokenizerRequired` = pas d'appel), prompt au-dessus du maximum autorisé refusé avant l'envoi, calibration après réponse.
- **Arrêt automatique** de la campagne sur usage inconnu, dépassement de la réservation ou tentative supplémentaire (`halt_reasons` : `UNKNOWN_USAGE`, `COST_BOUND_BROKEN`).

## Limites et ce qui reste à décider

- Règles **non appliquées** et sonde **non lancée** : l'effet réel du pare-feu est une hypothèse tant que le propriétaire ne l'a pas constaté.
- Les IP d'un fournisseur derrière un CDN changent : à relever à chaque fenêtre ; un échec de connexion hors de ces IP est voulu.
- Dépend du fournisseur : forme de la requête et de la réponse (le fournisseur de chat-completions est supposé), nom du paramètre de plafond de sortie, jetons de raisonnement, coût renvoyé. Non testé contre un vrai service.
- Le courtier comme **processus séparé** (serveur local) n'est pas construit : l'exécuteur de campagne autorisée reste à faire (ligne 8 de la matrice).
- Conteneur sans réseau (`--network none`) comme alternative au pare-feu : non conçu en détail.
