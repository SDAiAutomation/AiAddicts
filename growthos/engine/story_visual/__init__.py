"""Story Studio 2.0 — moteur de récit illustré (cartes éditoriales + voix off).

Module HORS LIGNE par construction : aucune fonction d'ici n'appelle un fournisseur payant par elle-même.
Les appels (images, voix, texte) passent par des *fournisseurs injectés* (voir `orchestrator.py`) ; les tests
et l'exemple déterministe utilisent des doublures sans réseau. Non branché sur le worker : aucun comportement
de production (Standard Video, Quiz, Story animé) n'est modifié par ce paquet.
"""
