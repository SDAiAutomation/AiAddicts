# Format Faceloop : chaîne de maths courte

## Promesse éditoriale

Chaque épisode pose un problème précis, laisse au spectateur un bref temps pour essayer, montre une transformation mathématique à la fois, vérifie la réponse et propose un exercice voisin dont la réponse n'est pas identique par défaut. Le hook doit annoncer une question réellement résolue dans la vidéo. Le texte parlé explique **pourquoi** chaque étape est permise ; le visuel montre **ce qui change**. Éviter les formules décoratives, les démonstrations qui sautent un passage essentiel et les promesses de réussite scolaire.

**Public de départ recommandé : collège / début lycée.** Les équations du premier degré et les fonctions affines tiennent dans des étapes courtes, lisibles sur téléphone et vérifiables exactement par le moteur actuel. C'est une hypothèse de produit à tester avec de vrais spectateurs, pas une affirmation sur la taille du marché ou sur une préférence de l'algorithme YouTube.

Premier cycle : six épisodes revus par une personne compétente en maths, répartis entre trois idées différentes : « trouve x », « repère l'erreur » et « vois la solution sur un graphe ». Varier l'accroche, le problème et la représentation ; ne pas répéter six fois le même habillage de sauvetage d'équation. Examiner pour chacun le choix de regarder, la durée moyenne de visionnage, les passages revus et les commentaires qui révèlent une incompréhension, avec leurs fenêtres et dénominateurs. Les résultats guident la série suivante sans prétendre prouver une causalité.

Le créateur de cette chaîne est compétent en maths et assure lui-même la revue pédagogique. La machine signale les cas à examiner ; elle ne remplace pas son jugement sur la clarté d'une explication.

Sources pour les métriques YouTube : [Analytics Shorts](https://support.google.com/youtube/answer/12942217?co=YOUTUBE._YTVideoType%3Dshorts&hl=en) et [moments clés de rétention](https://support.google.com/youtube/answer/9314415). Une relecture peut aussi signaler une explication peu claire ; elle ne prouve pas à elle seule que le passage plaît.

## Contrat de production actuel

Utiliser le pipeline Generate existant avec `visual_style: "motion_graphics"`, le format vertical `9:16` et des blocs courts. Voir [`content/scripts/exemple-maths.json`](../content/scripts/exemple-maths.json). Deux scènes structurées sont disponibles :

La voix est choisie par le circuit ElevenLabs actuel de Generate : voix explicitement fournie, `voice_id` du script, voix associée à la niche, puis voix par défaut (`engine/voices.py`). Les exemples maths utilisent actuellement la voix par défaut configurée ; ils n'introduisent ni fournisseur vocal ni réglage séparé. `engine/assembler.py` synthétise chaque bloc avec ses timings mot à mot ; `engine/visuals.py` transmet ces timings aux animations. Changer la voix suit donc le même parcours que pour les autres vidéos Faceloop.

- `equation_steps` : 2 à 4 égalités en `x`, chacune avec `equation` et éventuellement `explanation` (visible) et `spoken` (ancre temporelle). Les étapes apparaissent au moment de leurs expressions dans la voix si les timings ElevenLabs sont disponibles ; sinon elles suivent un rythme régulier. Si les ancres annoncées ne correspondent pas à la voix disponible, `quality_check` demande une revue. Une contradiction finale est colorée comme une erreur, pas comme une solution positive. Un bloc trop dense doit être scindé plutôt que d'afficher cinq lignes minuscules.
- `function_graph` : `slope`, `intercept`, bornes des axes et éventuellement `highlightX`. La droite est tracée progressivement ; `y` et le point sont calculés par le moteur. Les bornes doivent montrer la partie pertinente de la droite et le point retenu.

La prévisualisation locale permet de comparer plusieurs moments :

```powershell
python -m engine.motion_graphics.preview content/scripts/exemple-maths.json --block 2 --at 0,3,7,12 --duration 12 --out output/math-equation-contact-sheet.png
python -m engine.motion_graphics.preview content/scripts/exemple-maths.json --block 3 --at 0,3,6,8 --duration 8 --out output/math-graph-contact-sheet.png
```

Pour caler les étapes sur une voix réellement générée, ajouter `--words <dossier-de-generation>/audio/block-02.words.json`. Les `--at` et `--duration` sont relatifs au bloc. Une planche sans `--words` montre le rythme de repli, pas le timing final de la voix.

## Contrôles avant publication

1. Le script est refusé avant synthèse vocale si la résolution linéaire change l'ensemble des solutions ou si le calcul sort du domaine vérifiable. Le vérificateur traite les égalités en une variable `x` avec opérations rationnelles. Il ne certifie ni quadratiques, ni trigonométrie, ni preuves générales.
2. Un graphe dont les bornes ou le point mis en avant sont incohérents est refusé. Les valeurs visibles du point sont dérivées de la fonction.
3. Le rendu vérifie débordements, chevauchements et zone des sous-titres. Un problème mathématique arrivé directement au rendu masque la démonstration et force `quality_check`.
4. Le créateur vérifie la justesse pédagogique de la narration, la lisibilité sur téléphone, les pauses utiles et l'exercice final. Le contrôle algébrique ne valide pas une explication trompeuse ou incomplète.

## Extensions après essai sur de vrais épisodes

Ajouter les domaines un par un, avec un validateur et des exemples annotés pour chacun : fractions et pourcentages, fonctions quadratiques et factorisation, géométrie avec contraintes, puis statistiques. Pour les preuves plus ouvertes, conserver explicitement l'état « non vérifié » et une revue humaine. Mesurer la compréhension et la rétention des épisodes, pas seulement le nombre de vidéos rendues. Ajouter les domaines un par un reste la règle : le web n'a pas de second moteur mathématique et ne présente jamais comme vérifié ce que `math_validation.py` ne sait pas contrôler.


## Génération depuis Faceloop (web, depuis le 2026-10-05)

Il n'y a pas d'interface parallèle : un épisode de maths passe par le flux de création de script habituel.

1. Créer une niche dont le nom contient `math`, `algèbre` ou `équation` (par exemple « Mathématiques »), puis choisir le style **Motion Graphics**. C'est la seule détection : le web ajoute alors le contrat maths au prompt (`MATH_MOTION_PROMPT` dans `growthos-web/src/app/(app)/content/motion-graphics.ts`) et le gabarit narratif de la niche.
2. Saisir le sujet (« Résoudre 3x − 5 = 10 », « Où la droite y = 2x + 1 atteint-elle 9 ? »). Le script sort en **profil court** avec l'objectif `reach` (un épisode dure 15 à 40 secondes) ; le prompt impose `equation_steps` pour la dérivation (blocs de 2 à 3 étapes), `function_graph` pour une droite, `big_number` pour la vérification par substitution et `icon_text` pour le problème et l'exercice voisin.
3. Les ancres `spoken` sont cherchées dans la narration du bloc par le web (`alignSpokenAnchors`, même tokenisation que `sync.py`) : toutes les étapes sont donc synchronisées sur la voix et aucune vidéo ne part en `voice_sync_review` à cause d'une ancre introuvable.
4. Le moteur refuse la dérivation avant ElevenLabs si elle n'est pas vérifiable ou si elle change l'ensemble des solutions. La relecture pédagogique (clarté, rythme, exercice final) reste celle du créateur.

### Rendu : ce que le spectateur voit

- **Les étapes se lisent comme une transformation** : le texte qui change d'une égalité à la suivante (`− 3` des deux côtés, puis `8`) est affiché en couleur d'accent, la nouvelle étape glisse hors de la précédente, la précédente s'atténue, la dernière est verte (rouge si la dérivation conclut à une contradiction). Une différence de pure écriture (`2*x` contre `2x`) n'est pas mise en évidence.
- **La première étape est visible dès la première image** et une étape pas encore révélée ne dessine rien.
- **Lisibilité sur téléphone** : la pile d'équations s'adapte au nombre d'étapes (2 à 4) et occupe la zone de contenu (9 % à 58 % de la hauteur ; la bande du bas est réservée aux sous-titres et à l'interface de la plateforme). Mesuré par `preflight` sur 1080×1920 : texte minimal de 45 à 50 px, 4 étapes et légendes longues comprises.
- Tests : `tests/test_math_motion_graphics.py` (`TestMathLayoutReadability`, `TestEquationTransformation`).

### Rendre un épisode en local sans toucher à la base

`python main.py script.json` crée l'organisation, le compte et le contenu dans la base partagée et téléverse la vidéo : à éviter pour un essai. Pour un rendu local avec la vraie voix, appeler `engine.assembler._generate(data, output_root, None)` (aucune écriture en base) avec `venv/Scripts/python.exe`.
