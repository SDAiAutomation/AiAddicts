# Miniatures YouTube des quiz longs

Générées par `engine/thumbnail.py` (Pillow, aucun coût fournisseur), uniquement pour `quiz.recipe == "long"`.

## Trois variantes

| Id | Axe testé | Contenu |
|----|-----------|---------|
| A | sujet dominant | sujet, « QUIZ », pastille « N questions », cartes de réponse A–D (envoyée automatiquement à YouTube) |
| B | nombre dominant | sujet, « QUIZ », grand nombre de questions à la place des cartes |
| C | texte seul | sujet plus grand, « QUIZ », pastille, sans cartes |

B et C sont à téléverser à la main dans **Test & Compare** (YouTube Studio, ordinateur) : il n'existe pas d'API pour créer le test. YouTube désigne le gagnant au temps de visionnage, pas au CTR ; un résultat « sans gagnant » est normal sur une petite chaîne.

## Contrôles automatiques (`render_variant` → rapport)

- police minimale lisible à 168 px de large (≥ 8 px, soit ≥ 61 px à 1280) ; sujet ≥ 72 px, raccourci au dernier mot entier si nécessaire ;
- contraste texte/fond ≥ 3:1 (grands textes, WCAG) ;
- zone de la durée (20 % × 15 % en bas à droite) vérifiée au pixel ;
- poids JPEG < 2 Mo ;
- un sujet qui contient « % », « impossible », « garanti »… n'est jamais affiché (seul « QUIZ » reste) ;
- le nombre affiché est toujours le nombre réel de questions.

Ces contrôles sont analytiques (tailles et couleurs connues), pas une mesure du CTR.

## Niveau de preuve

Les règles viennent d'une recherche dont les sources officielles n'ont pas pu être ouvertes (voir le rapport « Miniature YouTube excellente quiz ») : aucune règle de design chiffrée n'est démontrée. Les choix ci-dessus sont des hypothèses à valider avec le test A/B, jamais des promesses de clics ou de vues.
