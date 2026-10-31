# Intégration minimale de Narrative Intelligence dans Faceloop (test A/B, fixtures locales)

**Objectif** : pouvoir *voir* Narrative Intelligence dans Faceloop au plus vite, sans aucun fournisseur, sans exécuteur, sans changement du comportement de production.

## Principe

1. **Backend (cette PR)** : le module reste inerte. Un drapeau `NARRATIVE_INTELLIGENCE_ENABLED` (défaut `false`) ouvre uniquement `faceloop.ui_fixture()` : une comparaison A/B de scripts **synthétiques**, passée hors ligne par la vraie chaîne (snapshot, validation, décision serveur), avec fournisseurs factices et garde réseau. Aucun import de `p0d/` (exécuteur, transport, journal).
2. **Frontend (PR séparée, growthos-web)** : une page de test lit un **fichier JSON local** (la fixture exportée) et l'affiche. Elle est masquée (404) tant que `NARRATIVE_INTELLIGENCE_ENABLED` n'est pas `true`. Aucune route d'API, aucune base de données, aucun appel au moteur.
3. **Aucun branchement** au worker, aux jobs, aux prompts de production, à Story Visual ni à Quiz.

## Écran « Comparaison de scripts A/B » (fixture locale)

- Une liste de 5 cas ; pour chacun, deux colonnes **A** et **B** : titre, blocs du script (rôle + texte).
- **Décision serveur** par variante : `accept`, `accept_with_notes`, `revise`, `review` (libellés français), avec la mention « décision calculée hors ligne sur données synthétiques ».
- **Indicateurs narratifs** par dimension (vérité, promesse, causalité, narrateur, clarté, fin) : `ok` / `réserve` / `bloquant` / `non évalué` — dérivés de la validation, **pas de note numérique inventée**. Les notes humaines 1–5 viennent du protocole d'évaluation humaine (non exécuté) et ne sont pas affichées.
- **Motifs** : pour chaque décision autre que `accept`, la liste des raisons (`established_blocker_f1`, `coverage_clarity_partial`, …) avec un libellé lisible, et les constats (code, dimension, gravité, citation, piste).
- **Comparaison** : indication « meilleure décision » (A, B ou égalité) calculée sur l'ordre `accept < accept_with_notes < revise < review`.
- Bandeau permanent : « Fixture locale synthétique — aucun modèle appelé ».

## Contraintes

- Aucune donnée réelle, aucun texte de prompt de production, aucune clé, aucun appel réseau côté serveur ni navigateur.
- Le drapeau frontend est indépendant du drapeau backend : tous deux désactivés par défaut.
- Pas de fusion automatique ni de déploiement : la PR frontend est ouverte, non fusionnée.

## Étapes ultérieures (hors de ce lot)

1. Remplacer la fixture par un export réel d'une campagne hors ligne (toujours sans fournisseur).
2. Après revue : un point d'entrée serveur en lecture seule qui sert la fixture.
3. Seulement ensuite, et avec autorisation explicite : essai en réseau isolé (protocole dédié), puis campagne réelle.
