# Faceloop : benchmark de référence du moteur motion graphics (phase A, 2026-10-10)

Aucun code de production modifié. Cinq vidéos verticales complètes rendues avec le pipeline actuel (`engine.assembler._generate`, la même fonction que le worker), hors dépôt. Les images ont été inspectées par moi à partir des MP4 rendus (planches contact toutes les 2 à 2,5 s + images pleine résolution). Aucune note chiffrée inventée : les constats sont qualitatifs et appuyés par des images ou du code.

## 1. Vidéos produites (hors contrôle de version)

Dossier : `C:\bo\deliverables\` (copies stables). Sorties brutes : scratchpad de la session et `C:\bo\`.

| # | Cas | Script source (existant) | Fichier |
|---|-----|--------------------------|---------|
| 1 | PocketLogic, finance EN | `content/scripts/pocketlogic/04-five-dollars-a-day.json` | `1-pocketlogic-invest-5-a-day.mp4` |
| 2 | Finance FR (voir limite 2) | `content/scripts/benchmark/b-finance.motion_graphics.json` | `2-epargne-3000-fr.mp4` |
| 3 | Maths, Manim | `content/scripts/exemple-maths.json` | `3-maths-2x3-11.mp4` |
| 4 | Explainer multi-éléments | `content/scripts/pocketlogic/02-raise-still-broke.json` | `4-explainer-raise-still-broke.mp4` |
| 5 | Récit, typographie cinétique | `benchmark/a-storytelling.base.json` avec `visual_style` = `flat_color` | `5-story-kinetic-nour.mp4` |

Planches contact : `pocketlogicm.png` (cas 4), `benchmark-ep.png` (cas 2), `maths.png` (cas 3), `benchmark-la.png` (cas 5), `trio.png` (images pleine résolution).

Limites de méthode, à lire :
1. **Planification de scènes non rejouée** : les scripts existants contiennent déjà leur `motion_graphic` (planification faite en amont par le front/LLM). Je n'ai pas relancé cette étape LLM (coût, hors périmètre moteur). Le moteur de rendu, lui, est le vrai.
2. **« ArgentSimple » introuvable** dans le dépôt : j'ai utilisé le script financier français de référence du benchmark. Ses textes sont écrits sans accents (« Epargne », « A retenir »), ce qui est un défaut du script, pas du moteur.
3. Le cas 5 est un script existant dont j'ai changé seulement `visual_style`, pour activer le chemin typographie cinétique (aucune autre modification).
4. Les cas 4 et 5 ont d'abord échoué sur Windows (`FileNotFoundError`, chemin trop long : dossier de sortie profond + titre long). Ce n'est pas un défaut du moteur sous Linux (worker), mais le chemin n'est pas protégé. Relancés avec un dossier de sortie court, voix déjà synthétisées réutilisées.
5. Une inspection de frames échantillonnées ne remplace pas un visionnage en temps réel : fluidité du mouvement et synchro audio sont jugées sur images fixes et sur les métriques du moteur, pas à l'oreille.

## 2. Performances mesurées

Machine : Windows 11, 4 cœurs logiques, Manim 0.21.0 + MiKTeX, ffmpeg 9.0.1, `MATH_RENDERER=manim`. Séquentiel (pas de parallélisme).

| Cas | Durée vidéo | Temps de rendu | Pic mémoire (arbre de processus) | CPU cumulé (échantillonné) | Taille | Format |
|-----|-------------|----------------|----------------------------------|----------------------------|--------|--------|
| 1 | 25,2 s | 153 s | 1 305 Mo | 122 s | 4,2 Mo | 1080x1920, 25 fps, H.264 |
| 2 | 20,6 s | 118 s | 1 245 Mo | 96 s | 3,6 Mo | idem |
| 3 (Manim) | 26,6 s | 172 s | 1 252 Mo | 92 s | 2,5 Mo | idem |
| 4 | 26,5 s | 151 s | 1 289 Mo | 116 s | 4,5 Mo | idem |
| 5 | 21,6 s | 119 s | 1 200 Mo | 92 s | 3,6 Mo | idem |

- Le rendu final seul (assemblage + encodage) dure environ 37 à 46 s ; le reste est surtout la voix (réseau) et le rendu des clips.
- Le CPU est une valeur plancher : les sous-processus déjà terminés ne sont plus échantillonnés.
- **Aucune défaillance de rendu** sur les 5 vidéos finales. Preflight sans erreur ni avertissement sur tous les blocs.
- **Coût externe** : seule la synthèse vocale ElevenLabs. Caractères synthétisés : 352 + 419 + 461 + 428 + 452 = 2 112 (cas 4 et 5 : synthétisés une seule fois, réutilisés au second passage). Aucun appel OpenAI/LLM (scripts déjà planifiés, aucune image IA). **Coût en dollars : non disponible** (`ELEVENLABS_USD_PER_1K_CHARS` non renseigné dans l'environnement local, donc le moteur ne le calcule pas).
- Aucune vidéo n'est enregistrée en base ni publiée (appel direct à `_generate`, pas à `run()`).

## 3. Constats visuels par vidéo

**Cas 1, PocketLogic.** Hiérarchie claire (un grand chiffre par scène, étiquette discrète au-dessus). Compteur animé lisible. Défauts : étiquette secondaire « ASSUMES 7% A YEAR, NOT GUARANTEED » collée sous le gros chiffre (presque sans espace) ; scène `before_after` correcte mais très statique ; trois scènes sur sept ne sont pas calées sur la voix (`synced: false`), donc leurs éléments arrivent sur un rythme régulier. Sous-titres propres, aucune collision, bande basse respectée.

**Cas 2, finance FR.** Même langage visuel, lisible. Défaut sémantique : la formule « REVENU − EPARGNE = BUDGET » s'affiche **« REVENU / EPARGNE / = BUDGET » sans le signe moins** (image `trio.png`, droite). Cause confirmée par exécution : `display_text.strip_directions` retire les tirets ASCII en tête de chaîne (`'- EPARGNE'` devient `'EPARGNE'` ; `'+ ...'` et le vrai signe moins `−` sont conservés). Une soustraction écrite avec un trait d'union est donc perdue à l'écran, ce qui change le sens de la formule. Autres points : le hook de 19 mots dépasse la cible (avertissement éditorial, score 80) ; absence d'accents (script).

**Cas 3, maths (Manim).** L'équation se transforme d'une étape à l'autre (les termes communs restent, « −3 des deux côtés » apparaît) : le meilleur mouvement des cinq vidéos. Vérification mathématique du moteur : `verified`, x = 4 (conforme : 2·4 + 3 = 11). Défauts : rupture de style visible entre les scènes Pillow (titre et vérification en sans-serif gras) et les scènes Manim (équations en serif LaTeX, titre « ISOLER x » en gris très atténué) ; l'étape « ÷2 des deux côtés » affiche brièvement des fragments superposés pendant la transformation (visible sur l'image mi-transition, à contrôler en temps réel) ; la scène d'intro ouvre sur un fond presque vide avec une petite équation.

**Cas 4, explainer.** Seule vidéo qui enchaîne plusieurs types de scènes (barres, répartition, formule). Barres et lignes de répartition lisibles et bien animées. Défauts : la première scène (`+$1,000`) puis une deuxième (`RAISE: +$1,000 A MONTH`) répètent la même information ; 4 scènes sur 7 non calées sur la voix ; chaque scène ne montre qu'une idée, sans lien visuel avec la précédente (pas de continuité d'un chiffre à l'autre).

**Cas 5, récit en typographie cinétique.** **Défaut le plus net des cinq.** (1) Les sous-titres un mot à la fois sont placés **au centre de l'écran** et se superposent au texte cinétique, également centré (`trio.png`, gauche : « OUBLIEE » écrase « BOITE A »). (2) Le texte cinétique est un extrait tronqué de la narration (« NOUR TROUVA UNE BOITE A… »), donc il double les sous-titres sans rien apporter. (3) Aucun visuel narratif : fond dégradé sombre unique pendant tout le récit, sans émotion ni changement de rythme. Cause confirmée dans le code : `captions.py` place les sous-titres en bande basse seulement si un bloc porte une clé `motion_graphic` (`is_motion`, ligne 467) ; en typographie cinétique la scène est construite au rendu, la clé n'existe pas, donc les sous-titres tombent au centre (`\an5`, ligne 509).

## 4. Défauts récurrents sur plusieurs vidéos

1. **Aucune transition ni mouvement de caméra** : toutes les vidéos sont des coupes franches (`motion_direction`: `transition: "cut"`, `moves` vides, `available: false`). 5 vidéos sur 5.
2. **Une idée statique par scène**, sans élément persistant d'une scène à l'autre : 5 sur 5 (le cas 3 y échappe en partie grâce à Manim).
3. **Scènes non calées sur la voix** : 3 de 7 (cas 1) et 4 de 7 (cas 4). Ces scènes utilisent l'apparition régulière au lieu de suivre la parole.
4. **Garde-fous de mise en page aveugles à la sémantique** : le preflight ne signale rien (zéro erreur) alors que le cas 2 perd un signe moins et que le cas 5 superpose texte et sous-titres. Le preflight mesure les boîtes de texte du moteur, pas les sous-titres incrustés ni le sens.
5. **Bas de l'image peu exploité** : le contenu occupe surtout 12 à 55 % de la hauteur, les sous-titres vers 69 %. Une partie du vide est voulue (zone de l'interface plateforme) ; à ne pas compter comme défaut sans mesure.

## 5. Priorisation (impact visuel x fréquence / (complexité + coût))

Heuristique qualitative, pas un score.

| Rang | Amélioration | Impact | Fréquence | Complexité / coût | Remarque |
|------|--------------|--------|-----------|-------------------|----------|
| 1 | Typographie cinétique : sous-titres en bande basse + texte cinétique non redondant et non tronqué | élevé (défaut visible, illisible) | tout le style `flat_color` (1 style sur plusieurs) | faible à modérée, local, aucun coût API | Cause de code identifiée |
| 2 | Signe moins perdu dans les formules | élevé (sens faux) | toute formule avec soustraction écrite « - » | très faible (quelques lignes + test) | Correctif, pas une refonte |
| 3 | Scènes calées sur la voix (ancres manquantes) | moyen | 7 scènes sur 14 mesurées | moyenne (dépend des scripts amont) | Partiellement un sujet de contenu |
| 4 | Transitions entre scènes | moyen | 5 sur 5 | faible à modérée (risque de décalage de durée avec la voix) | Pas prioritaire : d'autres défauts sont plus nets |
| 5 | Composition multi-éléments / continuité entre scènes | moyen à élevé | 5 sur 5 | élevée | À traiter après 1 à 4 |
| 6 | Cohérence de style Pillow/Manim sur les épisodes de maths | moyen | cas maths seulement | moyenne | |

Les transitions ne sont pas en tête : la typographie cinétique est visiblement cassée et une formule perd un signe, ce qui pèse plus que l'absence de fondu.

## 6. Plus petite amélioration viable (recommandation unique pour la phase B)

**Corriger la typographie cinétique (style `flat_color`) :**
1. Placer les sous-titres en bande basse pour ce style (traiter `flat_color` comme `is_motion` dans `engine/captions.py`, sans toucher aux autres styles).
2. Remplacer l'extrait tronqué de la narration par un texte qui ne double pas les sous-titres : mot fort ou phrase courte déterministe, et monter le bloc de texte dans la zone de contenu (au-dessus de la bande de sous-titres).
Fichiers concernés : `engine/captions.py`, `engine/kinetic_typography.py`, tests `tests/test_captions.py` et `tests/test_kinetic_typography.py`. Aucune dépendance, aucun appel API, retour arrière en rétablissant les deux fichiers.

À part, à approuver séparément : le correctif d'une ligne du signe moins (point 2 du tableau), car c'est une erreur de sens et non un choix de design.

## 7. Critères d'acceptation pour la comparaison avant/après

Mêmes scripts, mêmes voix (réutilisées), même machine, même dossier de sortie court.
1. Cas 5 : sur chaque scène, aucune superposition entre sous-titre et texte cinétique (contrôle visuel de toutes les scènes, y compris l'image au premier mot et au dernier).
2. Cas 5 : le texte cinétique n'est ni tronqué au milieu d'un mot ni un doublon mot pour mot des sous-titres du même instant.
3. Cas 1 à 4 : sous-titres à la même position qu'avant (comparaison d'images à instants identiques), aucune régression.
4. Durée de chaque vidéo identique à celle de la référence (écart nul), synchro voix inchangée.
5. Durée de rendu et pic mémoire dans la marge de variation mesurée (cas 5 : 119 s, 1 200 Mo ; la variation entre exécutions n'a pas été mesurée, donc à établir avec au moins deux rendus de référence).
6. Tests existants verts + au moins un test qui échoue avant le correctif (position des sous-titres en `flat_color`).
7. Aucun appel API supplémentaire.
