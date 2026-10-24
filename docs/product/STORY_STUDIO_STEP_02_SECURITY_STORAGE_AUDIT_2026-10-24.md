# Story Studio — Étape 2 : audit statique

Date : 2026-10-24. Aucun test, appel payant, déploiement ou changement de configuration effectué.

## Pipeline vérifié
- `growthos/engine/assembler.py` valide et modère avant réservation atomique du crédit ; rembourse en cas d'échec de génération ou d'upload.
- L'upload est limité par réencodage à environ 45 MiB, avec trois tentatives.
- `growthos/engine/repo.py` réclame les jobs par changement conditionnel de statut et applique une rotation entre organisations.
- Le worker utilise `service_role` ; l'isolation entre organisations exige des tests indépendants.

## Points à confirmer
- `growthos/engine/storage.py` décrit un bucket privé et des références signées côté frontend ; la migration historique `20260904110000_content_videos_bucket.sql` créait initialement un bucket public. Lire les migrations ultérieures et vérifier l'état réel avant de conclure.
- Les chemins de versions sont présentés comme immuables, mais la fonction générique d'upload utilise `upsert=true` ; vérifier la protection effective.
- `20260915120000_atomic_credit_reservation.sql` restreint les RPC de crédit à `service_role`.
- Les fichiers de tests Story Studio et Story Intelligence existent, mais aucun résultat d'exécution n'a été vérifié ici.
- Vérifier le comportement en cas de crash après réservation du crédit et avant publication.

## Décision
Conserver provisoirement queue, worker, voix, stockage et crédits ; construire l'animation comme adaptateur isolé. Ne pas modifier le bucket, les migrations, les flags ni les données en production pendant l'audit.

## Étape 3
Vérifier les migrations finales de confidentialité, les résultats CI et l'architecture des adaptateurs de rendu avant le prototype 2D offline.
