# Protocole d'évaluation humaine à l'aveugle et validation des sources (P0-D, Standard)

Statut : **protocole et outillage préparés, aucune évaluation réalisée, aucune source déclarée vérifiée.** Il adapte `05_EVALUATION_ET_PILOTE.md` (deux variantes Standard-A et Standard-B au lieu de quatre).

## Part 1 : validation humaine des sources S01 et S02 (sujet N05)

Seul le sujet N05 (documentaire, mode `fact`) dépend de sources. Elles sont `prepared_for_benchmark` : tant qu'un humain ne les a pas validées, toute décision documentaire reste `review` (verrou de provenance).

**Checklist** (gabarit `growthos/engine/narrative_review/fixtures/p0d/source_validation_S01_S02.template.json`, tous les états à `unverified`) :

1. Le relecteur est **indépendant** des auteurs des sources et des scripts ; il s'identifie (nom, rôle, date).
2. Ouvrir soi-même chaque URL (S01 `path.ox.ac.uk/centenary/the-discovery-of-penicillin/`, S02 `path.ox.ac.uk/centenary/our-history/`). Ne pas se fier au résumé.
3. Pour **chaque phrase du résumé** : copier une **courte citation textuelle de la page** (10 à 300 caractères) qui l'étaye, ou choisir `partially_supported`, `not_supported` ou `source_unavailable`.
4. Cinq contrôles par source : page accessible à l'URL consignée ; résumé original (pas une copie) ; localisateur pointant le bon passage ; affirmations autorisées dans ce que dit la page ; limites exactes (ni scène privée, ni citation, ni date exacte, ni nombre de vies sauvées pour S01 ; pas d'attribution individuelle pour S02).
5. Décision par source : `human_verified` (seulement si tout est `verified`), `needs_fix` ou `rejected`. Ne pas modifier les phrases du résumé : signaler le besoin de correction dans `note`.
6. `validate_record` vérifie la **complétude** (identité, indépendance, citations, dates, empreinte du corpus). Il ne prouve pas que la vérification a été bien faite et ne modifie aucun fichier. Le propriétaire reporte le résultat dans `sources_bornees.json` (`human_verified_by`, `human_verified_at`) : cela change l'empreinte du corpus et exige une nouvelle autorisation.

## Part 2 : évaluation à l'aveugle des scripts A/B

**Matériel.** 10 scripts (5 sujets x A/B), identifiés par des identifiants opaques issus d'une permutation seedée par la campagne. Les fichiers destinés aux humains ne contiennent ni sujet numéroté, ni condition, ni donnée `evaluator_only` (testé). La clé de démasquage (`PRIVATE_unblinding_key.json`) et les attentes d'évaluateur sont séparées et ouvertes seulement après la saisie.

**Auditeurs.** 12 adultes francophones correspondant à l'audience, non auteurs. Chacun évalue 5 récits, **un par sujet** : 60 évaluations, 3 auditeurs par script au minimum (6 par variante et par sujet). Variante `(r + t) mod 2`, ordre des sujets décalé de `r mod 5` et inversé pour les `r` impairs ; **aucun auditeur n'entend A et B du même sujet**. Une seule écoute, même lecteur ou même voix locale pour tous ; une lecture silencieuse est étiquetée « revue textuelle » et ne satisfait pas le critère d'écoute.

**Questions, dans cet ordre.** (1) « Quelle était l'idée ou la situation centrale ? » en réponse libre, **avant** toute question propre au sujet ; (2) la question de compréhension du sujet (clé dans le fichier privé), codée 0 / 1 / 2 ; (3) les cinq notes ; (4) défauts.

**Grille ancrée (1, 3, 5 ; 2 et 4 intermédiaires, aucune note manquante remplacée par 0).** Une note basse cite un passage ou le moment précis.

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| Qualité narrative | Succession de faits sans histoire ; on décroche | Histoire reconnaissable, un passage peu utile | Chaque étape fait évoluer l'attente ou la compréhension |
| Causalité | Contradiction majeure ou résolution arbitraire | Liens secondaires implicites mais reconstructibles | Conséquences et transitions intelligibles, aucune coïncidence non préparée |
| Clarté (une écoute) | Acteurs ou raisonnement impossibles à suivre | Une ambiguïté locale | Compréhension sans effort |
| Payoff (promesse tenue) | Réponse absente, contredite ou remplacée par une formule | Réponse présente mais peu préparée ou redondante | Réponse, choix ou conséquence complets, préparés et spécifiques |
| Factualité et honnêteté du mode | Fait inventé présenté comme réel, ou contredit par le dossier | Une affirmation non couverte, ou mode ambigu | Tout fait couvert par le dossier ; fiction reconnaissable ; aucune attribution inventée |

**Défauts.** Code, gravité, preuve (passage), « établi » ou « incertain », source consultée. Une bonne note ne masque pas un défaut bloquant.

**Panel éditorial.** 3 lecteurs distincts des auteurs comparent les 5 paires, côtés gauche/droite mélangés (A n'est pas toujours à gauche), avec le dossier factuel mais **sans** la critique du modèle ; préférence `left` / `right` / `tie` / `neither` + justification ; deux votes concordants font un gagnant, sinon paire indécise ; les votes initiaux sont conservés.

**Rappel à 24 h** (fenêtre 20 à 28 h), sans titre, script ni questionnaire précédent : récits rappelés et détail retenu, mappés ensuite aux identifiants. Hors fenêtre ou absent : manquant avec motif. Exploratoire.

**Agrégation.** Médiane par script, puis différence B − A **par sujet et par dimension** ; un script avec moins de 3 notes rend la paire **provisoire** (valeur `None`, jamais 0). Les 60 notes ne sont pas 60 sujets indépendants. Toute différence de durée supérieure à 15 % au sein d'une paire est signalée comme facteur de confusion, sans accélération ni coupe.

**Lecture des résultats.** 5 paires et 12 personnes : un signal de poursuite, pas une preuve statistique. Les critères de passage sont ceux de `05_EVALUATION_ET_PILOTE.md` §7 ; ils sont figés avant toute génération et ne sont pas déplacés après coup.

## Ce qui n'est pas fait

Recrutement, voix ou lecteur, saisie réelle, démasquage, rappel à 24 h ; aucune note n'existe.
