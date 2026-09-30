# Audit des langues — 30 septembre 2026

## Périmètre

Lecture du code de génération dans `growthos-web` : scripts manuels, adaptation de texte, séries, motion graphics, quiz, fiches personnages, analyse des accroches, suggestions de sujets et stratégie de compte. Vérification des paramètres de langue des formulaires, des catalogues de traduction et des chemins de rendu Python des quiz et du motion graphics.

Les tests utilisent des réponses IA simulées. Cet audit ne certifie pas la langue de chaque future réponse du modèle et ne remplace pas une vérification de vidéos générées.

## Corrections locales dans growthos-web

- Descriptions visuelles : le nettoyage utilise maintenant la langue du script. Le précédent correctif des prompts laissait encore le nettoyage français actif.
- Quiz : suppression des consignes contradictoires imposant des descriptions françaises et les choix « Vrai/Faux ». Tous les champs générés suivent la langue choisie, y compris leur nettoyage.
- Personnages : langue transmise depuis l'éditeur et depuis le script enregistré lors de la mise en génération. Extraction et nettoyage suivent cette langue ; la génération des séries reçoit aussi la consigne pour les descriptions des personnages.
- Analyse des accroches : commentaires dans la langue de l'interface, réécritures dans la langue choisie pour le script, même si le brouillon est déjà mélangé.
- Suggestions de sujets : titres dans la langue du contenu ; raisons et ancienneté dans la langue de l'interface. Les termes sources restent fidèles au flux original.
- Stratégie de compte : langue de l'interface au lieu du français imposé.
- Couvertures de quiz : retrait des titres anglais imposés par catégorie. Le titre saisi sert de proposition modifiable. La langue choisie à l'étape d'apparence est conservée lors du retour au parcours.

## Points restant à traiter

1. **Préréglages manuels de personnages** : `growthos-web/src/app/(app)/content/visual-styles.ts` contient des descriptions et contraintes françaises. `character-sheet.tsx::applyArchetype` les insère telles quelles. L'extraction IA est corrigée, mais ces préréglages nécessitent des traductions éditoriales pour les six langues. Les textes déjà saisis ne sont pas traduits automatiquement.
2. **Diagnostics éditoriaux** : `engine/editorial_quality.py` recherche des accroches, marqueurs et plans larges en français. L'hypothèse « visual toujours en français » n'est plus valable. Claude Code doit adapter le diagnostic à `script.language` et aux champs structurés de cadrage. Le frontend `src/lib/series-editorial-score.ts` a également une détection d'accroches génériques limitée au français. Ce sont des limites de diagnostic, pas une traduction du script.
3. **Contenu existant et choix manuels** : changer la langue ne traduit pas automatiquement un titre, un script enregistré, une fiche ou une couverture déjà saisis. Le mode d'import « conserver » garde volontairement le texte original sans appel IA.

## Contrôles

- 75 tests frontend et suivi des recommandations réussis, dont quatre nouveaux tests couvrant les six langues des quiz, l'extraction de personnages, les langues distinctes des analyses et l'ancienneté des tendances.
- Les tests de parité des traductions français/anglais et des clés d'interface passent.
- TypeScript, ESLint sur les sept fichiers source modifiés et `git diff --check` passent.
- Le rendu motion graphics lu utilise les textes fournis par le script ; aucun libellé français/anglais fixe supplémentaire identifié dans les scènes inspectées.
- Les phrases de narration des quiz disposent déjà de variantes pour les six langues dans `engine/quiz.py`.
- Aucune génération IA réelle, aucun déploiement, aucune modification des scripts stockés.

Les modifications du backend observées pendant cet audit appartiennent à un autre travail et n'ont pas été touchées.
