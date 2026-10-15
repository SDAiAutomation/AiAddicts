# API du runtime Explainer (version runtime 0.1.0)

Tu écris le CORPS d'une fonction `build(S)` : du JavaScript ES2017 qui DÉCLARE une scène animée. Tu ne dessines rien toi-même : tu crées des éléments, tu leur donnes des mouvements dans le temps, tu règles la caméra. Le runtime évalue tout à partir du temps `t` (rendu pur et déterministe).

## Format de sortie
Un seul bloc ```js contenant uniquement le corps de la fonction (pas de `function build`, pas d'`export`). Commentaires courts en français autorisés.

## Ce qui est autorisé (le reste est refusé par l'analyse statique)
- Variables `const`/`let`, boucles `for` (avec condition d'arrêt) et `for...of`, `if`, fonctions fléchées, `.map/.forEach/.slice/.join`, littéraux d'objets et de tableaux, gabarits `` `...` ``, opérateurs.
- Globales : `S`, `Math` (abs sin cos tan atan atan2 PI pow min max floor ceil round sqrt exp log sign hypot trunc — PAS `Math.random`), `hash(a,b)` (hasard déterministe entre 0 et 1), `W`=1080, `H`=1920, `Number`, `String`.
- INTERDIT : `new`, `this`, `while`, `try`, `class`, `switch`, `fetch`, `window`, `document`, `Date`, `eval`, `constructor`, `?.`, `??`, accès DOM, réseau, tout `import`.

## Repère
Canevas 1080 × 1920 (9:16). `x` vers la droite, `y` vers le bas, centre de l'écran = (540, 960). Zones à éviter pour tout texte important : haut (y < 160), bas (y > 1650), bord droit (x > 950).
Temps : secondes LOCALES au plan (0 = début du plan, `S.dur` = sa durée).

## La scène `S`
- `S.dur` : durée du plan. `S.t('id')` : instant (s) d'une ancre déclarée dans le plan (le mot de la voix off qui déclenche l'action). Utilise-les : chaque action importante doit tomber sur son ancre.
- `S.sky('night'|'dusk'|'day'|'void')` : fond. `S.grid(true)` : fond technique à points (avec `'void'`).
- `S.add(kind, props)` : crée un élément, renvoie un handle `h`.
- `S.cam.set(t, {x,y,z,r})` / `S.cam.to(t0, t1, {x,y,z,r}, ease)` : caméra (centre visé x,y ; zoom z ; rotation r en radians). Départ : x=540, y=960, z=1. Une caméra qui bouge lentement en permanence donne de la vie.
- `S.sfx(t, type)` : bruitage. Types : tick, pop, clip, unclip, whoosh, whooshDown, drop, impact, glitch, split, bits, blip, scan, ping, hit.
- `S.fade(t0, t1, 'bg', 'in'|'out')` : fondu de la scène entière (rarement utile : les raccords entre plans sont gérés ailleurs).

## Un élément `h`
Props communes (toutes animables si numériques) : `x, y` (position), `s` (échelle), `a` (opacité 0..1), `r` (rotation, radians), `hud` (true = collé à l'écran, ignore la caméra : pour mots-clés et légendes), `par` (parallaxe 0..1, <1 = plus lent que la caméra, pour l'arrière-plan), `layer` (ordre de dessin, plus grand = devant).
Méthodes (toutes renvoient `h`) :
- `h.appear(t, dur=0.4, how='pop'|'up'|'left'|'right')` : l'élément est invisible avant `t`, puis apparaît.
- `h.hide(t, dur=0.3)` : disparaît.
- `h.to(t0, t1, {prop: valeur}, ease='io')` : anime des props numériques de leur valeur courante vers la valeur donnée entre t0 et t1. Pour une prop non numérique (texte, tableaux), la valeur change à t0.
- `h.set(t, {prop: valeur})` : change une prop instantanément à `t` (ex. un texte qui se tape, un tableau de bulles).
- `h.pulse(t, amount=0.18, dur=0.35)` : petit rebond d'échelle (met en valeur).
- `h.follow(points, t0, t1, ease='io')` : l'élément suit la ligne brisée `[[x,y],...]` entre t0 et t1 (remplace x,y).
Easings : `'io'` (doux, par défaut), `'out'` (freine à l'arrivée), `'inn'` (accélère), `'back'` (léger dépassement), `'lin'`.
Règles : appelle `h.to` dans l'ordre chronologique pour une même prop ; une valeur de prop avant son premier `to` est celle donnée à la création.

## Éléments (`kind` et props propres, valeurs par défaut entre parenthèses)
Couleurs : un jeton (`ink`, `dim`, `bg`, `panel`, `chip`, `primary` cyan, `accent` orange, `warm` ambre, `good` vert, `violet`, `blue`, `yellow`, `white`) ou une couleur CSS `#rrggbb`.
- `text` : `text`, `size`(64), `weight`(700), `color`('ink'), `mono`(false), `glow`(0), `maxW`(0, réduit la taille pour tenir), `ls`(0). `\n` = retour à la ligne. Centré sur (x,y). Mots-clés : 64 px minimum.
- `box` : `w`(200), `h`(100), `r`(16), `color`('panel'), `stroke`(''), `sw`(3). Centré.
- `circle` : `rad`(40), `color`, `stroke`, `sw`, `glow`.
- `line` : de (x,y) vers (x+dx, y+dy) ; `dx`, `dy`, `w`(6), `color`, `draw`(1 : proportion tracée, animable de 0 à 1), `dash`(null ou [12,12]), `glow`, `head`(true = pointe de flèche).
- `polyline` : `points` (coordonnées RELATIVES à (x,y)), `w`, `color`, `draw` (0..1), `glow`, `fill` (couleur de surface sous la courbe, jusqu'à y=0 local). Courbes de données : calcule les points en JS.
- `chunk` : bloc de protocole/paquet. Centré horizontalement, y = centre : `w`(200), `h`(72), `color`('accent'), `label`, `size`(28), `mono`(true), `glow`.
- `bubble` : bulle de message : `text`, `color`('accent'), `tc`('dark'), `size`(40).
- `phone` : téléphone de messagerie générique (560×1100 à s=1 ; utilise s≈0.8-1.0 pour un gros plan) : `contact`, `avatar`, `input` (texte en cours de frappe), `press`(0..1, animer le bouton d'envoi), `bubbles` : tableau de `{edge, y, text, side:'left'|'right', col, tc}` (coordonnées dans le repère du téléphone : edge = bord extérieur, -244 à gauche / 244 à droite ; y entre -420 et 420 ; `col` jeton, `tc` couleur du texte).
- `miniphone` : petit téléphone : `label`, `glow`.
- `person` : personnage plat assis (origine = hanches, regarde vers +x, `flip`:true pour regarder à gauche) : `pose` ('sitPhone' | 'sitHappy' | 'sitRead'), `skin`, `hair`, `style` ('short'|'curly'|'braids'|'bun'), `top`, `pants`, `typing`, `glow`, `pid` (identité). Garde exactement les mêmes props pour un même personnage d'un plan à l'autre.
- `house` : maison en coupe (origine = bas, centre) : `palette` ('dakar' chaude | 'paris' froide), `flip`, `dark`. Le canapé est calé pour un `person` posé à (x−120, y−106) échelle 1.
- `tower` : antenne (origine = pied) : `h`(470), `act`(0..1 : ondes radio animables).
- `city` : skyline de nuit (origine = pied, bord gauche) : `count`, `seed`, `far`(true = plus sombre), `minH`, `varH`.
- `router` (`hot` 0..1), `antenna` (`act`), `lock` (cadenas), `datacenter` (`w`,`h`, origine = bas centre).
- `water` : étendue d'eau avec rayons (origine = surface, centre) : `w`, `h`. `fish` (`color`,`dir`), `whale` (`dir`), `boat`.
- `particles` : `n`, `seed`, `w`, `h` (zone centrée sur x,y), `speed`, `dirx`, `diry`, `size`, `color`, `alpha`.
- `counter` : nombre animé : `value` (animer avec `h.to`), `decimals`, `prefix`, `suffix`, `size`, `color`, `glow`. Séparateur de milliers automatique.
- `bars` : histogramme vertical (origine = pied, centre) : `values`, `labels`, `w`, `h`, `color`, `grow` (0..1, animer), `size`.
- `golden` : rectangles d'or et spirale : `base`, `n`, `draw` (nombre d'étapes tracées, animable), `color`.

## Règles de réalisation (elles seront vérifiées)
1. UN seul point focal à la fois. Pas d'image figée plus de 1,5 s : quelque chose bouge (caméra, apparition, pulse, particules).
2. Chaque phrase de la voix off fait bouger quelque chose de signifiant. Les actions importantes tombent sur leur ancre (`S.t`), à ±150 ms.
3. Aucun texte coupé par le bord de l'écran, aucun chevauchement de textes. Mots-clés ≥ 64 px, contraste fort, hors zones d'interface.
4. On doit comprendre le mécanisme sans le son.
5. N'invente AUCUN chiffre : n'affiche que ceux fournis par le plan.
6. Décor et personnages cohérents avec la bible (mêmes couleurs, mêmes props).
7. Le plan doit s'exécuter vite (pas de boucles de milliers d'itérations).
