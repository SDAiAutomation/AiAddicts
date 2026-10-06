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

1. Le script est refusé avant réservation de crédit et synthèse vocale si la résolution change l'ensemble des solutions, saute plusieurs opérations en une seule étape ou sort du domaine vérifiable. Le vérificateur traite exactement les égalités en une variable `x` avec nombres rationnels et écritures usuelles comme `2x`, `(1/2)x`, `2(x+3)` et `0,5x`. Il accepte une réécriture algébrique, l'ajout d'une même expression linéaire aux deux membres ou leur multiplication par un même rationnel non nul. Deux scènes `equation_steps` consécutives doivent reprendre la même équation à leur jonction. Il couvre aussi un sous-ensemble précis des quadratiques factorisables ; il ne certifie ni racines irrationnelles, ni trigonométrie, ni preuves générales.
2. Un graphe dont les bornes ou le point mis en avant sont incohérents est refusé. Les valeurs visibles du point sont dérivées de la fonction.
3. Le rendu vérifie débordements, chevauchements et zone des sous-titres. Un problème mathématique arrivé directement au rendu masque la démonstration et force `quality_check`.
4. Le créateur vérifie la justesse pédagogique de la narration, la lisibilité sur téléphone, les pauses utiles et l'exercice final. Un libellé symbolique explicite (`−3`, `÷2`, `×6`) est comparé à la transformation réelle ; le contrôle ne certifie pas qu'une justification en prose ou la voix décrit correctement l'opération. Une revue humaine reste nécessaire. Le guide de l'Institute of Education Sciences recommande d'analyser les étapes des exemples résolus et d'employer un langage mathématique précis : [guide algèbre](https://ies.ed.gov/ncee/wwc/practiceguide/20), [résumé des recommandations](https://ies.ed.gov/ncee/wwc/Docs/practiceguide/wwc_algebra_summary_072115.pdf).

### Fractions à dénominateur constant

Le vérificateur accepte les coefficients rationnels, les fractions imbriquées à dénominateur numérique, les nombres mixtes (`1 1/2x`), les décimales françaises (`0,5x`), le trait de fraction `⁄`, les glyphes usuels comme `½`, `:` pour la division et les crochets de regroupement. Exemple exact : `(x+1)/2 + (x-2)/3 = 4` → `3(x+1)+2(x-2)=24` → `5x-1=24` → `5x=25` → `x=5`. Pour l'enseignement, chaque flèche doit correspondre à une opération justifiée et l'étape de suppression des dénominateurs doit être expliquée à voix haute.

Écrire `(1/2)x` pour « un demi de x » et `1/(2x)` pour « un sur deux x ». Les formes `1/2x`, `1/2(x+1)` et `x/2/3` sont refusées car leur regroupement est ambigu.

### Inconnue au dénominateur

Le vérificateur accepte désormais un quotient de deux expressions linéaires, avec au plus une telle fraction par membre et des opérations simples avec une constante. Il suit exactement les valeurs interdites. Par exemple `1/(x-1)=2` donne `x=3/2` avec `x ≠ 1` ; `(x-1)/(x-1)=0` n'a aucune solution. La restriction apparaît dans le titre de la scène, reste visible dans les scènes de résolution consécutives et force `domain_review` avant publication pour vérifier aussi l'explication orale. Une identité avec trou dans le domaine, une réduction quadratique ou des fractions rationnelles imbriquées restent non vérifiées. Les transformations qui effacent une valeur interdite doivent conserver le même ensemble de solutions.

### Équations du second degré factorisables

Le moteur reconnaît `x^2`, `x²`, `(x-2)(x-3)` et `(x-2)^2`. Il calcule le discriminant exactement et certifie les racines rationnelles, y compris une racine double ou l'absence de racines réelles. Pour afficher deux racines, la dernière étape peut écrire `x=2 ou x=3`, uniquement après une forme factorisée égale à zéro. Exemple : `x²-5x+6=0` → `(x-2)(x-3)=0` → `x=2 ou x=3`. Une branche manquante ou fausse est rejetée ; un discriminant positif non carré reste à revoir. La règle du produit nul et la vérification par substitution sont décrites dans [OpenStax, Algebra 1](https://openstax.org/books/algebra-1/pages/8-9-2-using-factored-form-and-the-zero-product-property).

### État du moteur au 6 octobre 2026

Le vérificateur exact couvre les équations linéaires, certaines équations rationnelles à dénominateur linéaire et les quadratiques factorisables à racines rationnelles. Il suit les valeurs interdites dans les scènes consécutives. La narration et la pédagogie demandent encore une revue humaine ; les équations rationnelles déclenchent explicitement `domain_review`. Prochaine validation produit : tester une petite série d'épisodes avec des apprenants et des enseignants, observer les incompréhensions et ajuster les explications avant d'ajouter un autre domaine.

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

### Rendu Manim (3Blue1Brown) des scènes maths

`equation_steps` et `function_graph` peuvent être rendues par **Manim** (`engine/motion_graphics/manim_backend.py`) au lieu de Pillow : formules composées par LaTeX, et l'équation **se transforme** d'une étape à la suivante (les morceaux communs glissent, les nouveaux arrivent, le texte qui change est en couleur d'accent, l'étape précédente s'atténue). Même contrat que le rendu Pillow : clip muet à la durée exacte du bloc, révélations calées sur la voix, mêmes couleurs de thème, même zone de sécurité.

- **Choix du moteur** : variable d'environnement `MATH_RENDERER` : `auto` (défaut : Manim s'il est installé), `manim` (le demande), `pillow` (jamais Manim).
- **Jamais bloquant** : Manim tourne dans un sous-processus avec délai maximal (`MANIM_TIMEOUT_SECONDS`, 300 s) ; toute erreur (Manim absent, LaTeX absent, plantage, délai) retombe sur le rendu Pillow, avec une ligne dans le journal. Sans LaTeX, le texte natif de Manim remplace `MathTex`.
- **Installation locale** : `pip install -r requirements-manim.txt` ; sous Windows `winget install MiKTeX.MiKTeX` ; sous Ubuntu `sudo apt-get install -y libcairo2-dev libpango1.0-dev pkg-config texlive-latex-base texlive-latex-extra texlive-fonts-recommended dvisvgm`.
- **Worker GitHub Actions** : l'installation est **optionnelle et éteinte par défaut**. Pour l'activer : variable de dépôt `MATH_RENDERER` = `manim` (Settings > Secrets and variables > Actions > Variables). Même activée, Manim + LaTeX (environ 2 min 15 s mesurées sur le runner) ne sont installés que si `scripts/queue_needs_manim.py` voit un épisode de maths en file : les autres vidéos ne paient rien. Mesuré sous Ubuntu : équation 5,5 s, graphe 3,3 s. Le workflow `growthos-manim-smoke.yml` (lancement manuel) valide l'installation et le rendu sous Ubuntu sans toucher au worker.
- **Contrôle local** : `python scripts/manim_smoke.py sortie/` rend une équation et un graphe et mesure le temps (environ 30 s chacun, LaTeX compris, première exécution plus lente).
- Tests : `tests/test_manim_backend.py` (le test de rendu réel est ignoré si Manim n'est pas installé). L'aperçu `python -m engine.motion_graphics.preview` reste en Pillow.
