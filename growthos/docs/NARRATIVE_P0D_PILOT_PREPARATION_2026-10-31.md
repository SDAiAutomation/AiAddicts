# Préparation hors ligne du pilote P0-D Standard : rapport

Date : 2026-10-31. PR #104 (brouillon). Statut : **préparation uniquement, aucun pilote lancé, aucun appel réseau ni payant.** Décision d'autorisation : voir « Prérequis manquants ».

## Périmètre préparé

- Sujets : N01, N04, N05, N13, N18 (split `pilot`). Strate : `standard` seulement (Story Visual est hors de ce lot : son validateur v1 est dans la PR #103).
- Conditions : A = baseline figée, B = A + diff de politique déclaré (`standard.structure`, `standard.policy_addendum`). Le message utilisateur, le modèle, les plafonds (16 000 jetons d'entrée, 4 000 de sortie, 90 s) et les réglages sont identiques. Une dérive de B hors « A + diff déclaré » fait échouer `conditions_report` (testé).
- Volume : 10 cases (5 sujets x 2 conditions), 1 appel de rédaction par case, au plus 1 appel de critique par script exploitable : **20 appels logiques au maximum**, 0 retry.
- Rien d'autre n'est accessible au runner : sujets de développement et de réserve refusés (`HoldoutAccessError`), valeurs `evaluator_only` détectées dans tout payload sortant (`LeakError`), fournisseur non déclaré hors ligne refusé, accès réseau bloqué pendant la campagne, retry caché ou dépassement de réservation = arrêt de la campagne.

## Baseline A reproductible (Mission 2)

- Les dépendances à des chemins temporaires ou locaux sont supprimées : `render_standard_A.js` (qui lisait un `node_modules` et un fichier temporaires) est remplacé par `fixtures/render_standard_A.mjs` (Node >= 22.13, aucun paquet npm, entrée = un checkout passé en argument, assemblage par marqueurs).
- `baseline_manifest.json` v0.2 fige, pour Standard, le commit de `growthos-web` (`c61480d6`) et le SHA-256 de chacun des 5 fichiers sources utilisés, et, pour Story Visual, le commit AiAddicts `57af0ae…` (PR #103) et le SHA-256 de `formats.py`. Les empreintes sont calculées sur le texte normalisé (fins de ligne LF) : un checkout Windows (CRLF) donne le même résultat.
- Vérification : `python -m growthos.engine.narrative_review.harness.rebuild_baseline --web-checkout <chemin> --engine-checkout <chemin>` (code de sortie 1 au moindre écart). Les sources ne sont **pas copiées** dans ce dépôt.
- **Preuve exécutée dans un environnement indépendant du worktree** : dossier temporaire neuf, clone neuf de la branche de la PR (`2c80b2c`), clones neufs de `growthos-web` à `c61480d6` et d'AiAddicts à `57af0ae`. Résultats : reconstruction **identique octet pour octet** pour Standard (SHA-256 `e270fe3e…`, 20 442 caractères) et Story Visual ; une source modifiée dans une copie est détectée (« script-length.ts differs from the frozen source », code 1) ; la répétition à blanc exécutée dans ce clone produit des fichiers **identiques octet pour octet** à ceux du worktree (24 fichiers) ; les 132 tests du paquet passent dans le clone avec les checkouts figés (aucun test sauté).
- Limite : la vérification exige l'accès aux deux dépôts (`growthos-web` est privé). Sans eux, les tests de reconstruction sont sautés avec un message explicite ; un test sauté n'est pas une preuve.

## Journalisation reproductible (Mission 3)

Écrits dans le dossier de campagne : `campaign_manifest.json` (plan complet écrit **avant** tout appel : cases, versions, empreintes du corpus, des sources et de la baseline, modèles, tarifs ou `null`, plafonds, 0 retry), `inputs/B*.json` (prompt système et utilisateur exacts, empreinte, diff de politique, plafonds), `B*.json` (sortie brute, jamais réparée), `registre_executions.csv` (colonnes du protocole, une ligne par tentative, écrite au fil de l'eau, chemins relatifs, coût estimé et coût observé séparés, inconnu = vide), `campaign_report.json` et `pilot_preparation.json`. Deux répétitions à blanc donnent des fichiers identiques octet pour octet.

## Résultats de la répétition à blanc (fournisseurs factices)

10 cases, 20 appels logiques (10 rédactions + 10 critiques), 0 tentative réseau bloquée, 0 arrêt, 0 retry. Elle ne mesure aucune qualité narrative : les fournisseurs factices ne jugent rien.

## Estimation du pilote (ESTIMATION, pas une mesure)

| | Jetons d'entrée | Jetons de sortie |
|---|---|---|
| Attendu (rédaction + critique) | 66 000 à 148 000 | 25 000 à 55 000 |
| Plafond dur (20 appels x 16 000 / 4 000) | 320 000 | 80 000 |

Base : taille réelle des 10 prompts figés (environ 21 000 caractères chacun, 2 à 4 caractères par jeton) ; sorties = hypothèses à remplacer par des mesures au premier essai réel. Hors jetons de raisonnement facturés (inconnus). **Aucun montant en dollars n'est annoncé** : le modèle et les tarifs datés ne sont pas fixés (`projected_usage(rows, prices)` calcule le coût dès qu'un tarif réel est fourni).

## Prérequis manquants pour P0-D (rien de ceci n'est fait)

1. **Décision sur la confidentialité de la baseline.** `fixtures/standard_A_fr_youtube.txt` est le prompt système Standard de production (environ 20 000 caractères) et se trouve dans un dépôt **public** (AiAddicts), depuis la première version de la PR (`7b6d0cc`) ; il reste dans l'historique git même si on le retire. À trancher par l'utilisateur avant toute fusion : garder, déplacer vers un dépôt privé, ou ne conserver que l'empreinte et la procédure de reconstruction.
2. **Autorisation explicite et distincte de l'utilisateur** pour les appels payants, avec modèle, tarifs datés et plafond monétaire global approuvés.
3. **Coupure de sortie au niveau du système d'exploitation et instrumentation du transport.** La garde actuelle est un crochet CPython (pas un bac à sable OS) ; `http_attempts` est déclaré par le fournisseur. Un adaptateur de fournisseur réel qui compte les tentatives réseau, les jetons et les charges n'existe pas encore.
4. **Tokenizer du modèle choisi** pour remplacer le majorant de 2 caractères par jeton.
5. **Relecture humaine des sources S01 et S02** (sujet N05) : tant qu'elles sont `prepared_for_benchmark`, toute décision documentaire reste `review`.
6. **Logistique d'évaluation humaine** : 12 auditeurs francophones, 3 relecteurs indépendants, rappel à 24 h, lecteur unique ou voix locale (voir `05_EVALUATION_ET_PILOTE.md`).
7. **Écarts connus entre la baseline et la production** : seul le texte du prompt système est figé ; message utilisateur, nettoyage, retries et revue du narrateur de la production ne sont pas reproduits.
8. **Faux refus attendus** : nombres écrits en toutes lettres, constantes dans une expression, calculs arrondis (sujet N13, simulation chiffrée) ; ils produiront `review` et devront être comptés comme non évaluables, pas comme défauts éditoriaux.
9. **Mode `fact`** (sujet N05) : sans affirmations factuelles enregistrées par le critique, la décision reste `review` (voulu).
10. **Critique jamais exécuté sur un vrai modèle** : le gabarit du critique et les 20 cas critiques n'ont pas été scorés ; le premier essai réel mesurera aussi les faux refus.
11. **Hors périmètre de ce lot** : JCS/RFC 8785 (bloquant avant intégration inter-langages), validateur Story Visual v1 (attend la PR #103), audit des textes affichés hors `dialogue`/`narration`/`on_screen_text` pour Story dialogué et Story Visual.

## Vérifications exécutées (hors réseau, `OPENAI_API_KEY` vide)

Voir la description de la PR #104 pour les commandes, le SHA et les résultats exacts.
