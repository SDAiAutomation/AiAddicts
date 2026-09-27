# Recommandations → scripts → observations

Contrat v1 partagé par `engine/recommendation_tracking.py` et
`growthos-web/src/lib/recommendation-receipt.ts`.

## Hypothèse et référence

`recommendations.experiment` contient une hypothèse principale :

- `version: 1`, `hypothesis` ;
- `target: {kind: archetype | hook | format, label, direction: favor | avoid}` ;
- `selection_method`, `sample_size`, `observed_score_lift` : justification de
  sélection, sans estimation d'effet causal ;
- `baseline`: médiane du pourcentage moyen regardé des 200 dernières vidéos
  au maximum ayant un relevé complet avec au moins 50 vues. Chaque vidéo ne
  compte qu'une fois. Valeur, effectif, méthode, identifiants/timecodes des
  relevés et bornes temporelles sont conservés.

La sélection réutilise les insights existants : groupes d'au moins trois
vidéos, écart d'au moins cinq points du score interne à la médiane du compte.
Ce score composite ne représente pas des points de rétention. Les autres
observations de la recommandation restent du contexte ; une seule hypothèse
est identifiée comme test principal. Les personnages récurrents restent autorisés.

## Reçu de génération

Le serveur capture la recommandation avant l'appel IA et retourne un reçu
signé après une génération réussie. Il contient :

- compte et organisation, identifiant de génération, date ;
- copie exacte de `id`, `generated_at`, `body`, `reasoning`, `confidence`,
  `experiment` de la recommandation ;
- `injected_brief` : texte effectivement envoyé dans le prompt ;
- version de l'intégration au prompt, modèle, empreinte du contenu produit.

Transport et stockage : `script.recommendation_receipt`, chaîne
`base64url(JSON).base64url(HMAC-SHA256)`. Domaine de signature :
`faceloop-recommendation:v1:` suivi du payload encodé. La clé est la
`SUPABASE_SERVICE_ROLE_KEY` serveur existante, jamais envoyée au navigateur.
Le frontend et le moteur doivent utiliser la même clé. Une rotation rend les
anciens reçus non vérifiables : ils restent stockés, mais ne sont plus
attribués par le diagnostic. Ne pas afficher une validation dans ce cas.

L'action de sauvegarde vérifie signature, compte et organisation. Elle ne
relit pas la recommandation courante, qui peut avoir changé entre-temps.
La génération de séries utilise le même contrat. Scripts et quiz manuels,
adaptation et inspiration de texte transportent le reçu jusqu'à la sauvegarde.
Le mode de conservation du texte, sans IA, ne crée aucun reçu. Une régénération
remplace le reçu actif ; pour un quiz, la régénération d'une question peut donc
porter sur une partie du contenu. Le contenu final diffère alors de l'empreinte
générée, ce qui est indiqué. Ce n'est pas un journal de tous les appels IA.

L'empreinte narrative est le SHA-256 du JSON compact UTF-8 d'une liste ordonnée
de chaînes nettoyées aux extrémités : titre, format, puis rôle/texte/visuel de
chaque bloc non vide. Pour un quiz : titre, `quiz`, sujet, introduction,
conclusion, puis question, choix, index de réponse en chaîne, explication.
L'empreinte de rapport ajoute à cette empreinte narrative le style visuel
(`default` par défaut) et les sous-titres (`bold_stroke` par défaut).

## Diagnostic et observations

`content_items.recommendation_report` est dérivé, versionné et lié aux
empreintes du script. L'interface masque un rapport qui ne correspond plus
au contenu. Les éditions via l'action de sauvegarde invalident le rapport
et la classification de l'histoire. Les écritures Python du rapport utilisent
`id`, `account_id` et `updated_at` pour éviter une écriture sur un script
modifié pendant le calcul.
Un trigger sans privilèges élevés actualise `updated_at`, invalide les deux
diagnostics et avance le `script_version` existant à chaque changement du JSON
script. Il ne double pas l'incrément déjà effectué par le trigger des séries.
Cela couvre aussi les éditions d'un script manuel ou déjà publié ; les mesures
de sa version précédemment rendue ne sont pas attribuées à la nouvelle.

- `application.status`: `consistent`, `not_observed` ou `needs_review`.
  Le format est comparé aux réglages sauvegardés. L'archétype et l'accroche
  utilisent le classifieur existant uniquement si sa version et son empreinte
  correspondent au script. Un modèle absent, une classification ancienne ou
  `autre` ne prouvent pas l'application. Aucune nouvelle boucle payante n'est
  ajoutée ; le classifieur existant reste opt-in via `LEARNING_MODEL`.
- `outcome`: dernier relevé de la vidéo avec sa date et ses valeurs, comparaison
  avec la référence figée, en points de pourcentage moyen regardé. Le dernier
  relevé incomplet reste incomplet : aucune fusion avec une ancienne mesure.
  Données manquantes, vues insuffisantes, ancienne génération/version rendue,
  absence de référence ou vidéo déjà incluse dans la référence empêchent
  la comparaison.
- `causal: false` : les vidéos n'ont pas été randomisées et peuvent avoir des
  anciennetés, sujets et audiences différents. Un écart observé ne prouve ni
  l'effet de la recommandation ni sa bonne application, et ne prédit pas de vues.

Le recalcul quotidien existant (`refresh_learning.py`) et la saisie CLI
(`log_metrics.py`) actualisent les rapports. Les brouillons sans mesure sont
présentés comme en attente ; une classification narrative peut attendre les
premières mesures. L'absence de reçu sur les anciennes vidéos reste inconnue.

## Livraison et vérification

1. Appliquer `supabase/migrations/20260926182849_recommendation_tracking.sql`.
   Deux colonnes JSONB optionnelles et un trigger d'invalidation, aucune
   nouvelle table ni règle RLS.
2. Livrer ensemble les changements serveur de growthos-web et du moteur.
3. Le prochain recalcul produit les hypothèses structurées. Une ancienne
   recommandation textuelle est conservée telle quelle et indiquée à vérifier.
4. Vérifier un nouveau script, sa sauvegarde, puis son rapport après saisie
   des mesures. Ne pas attribuer rétrospectivement une recommandation aux
   scripts créés avant ce contrat.

Tests sans appels payants : `tests/test_recommendation_tracking.py`,
`tests/test_learning.py`, `growthos-web/scripts/recommendation-tracking.test.mjs`
et suite frontend existante.
