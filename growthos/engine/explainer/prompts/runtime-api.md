# API du runtime Explainer (version runtime 0.1.0)

Tu écris le CORPS d'une fonction `build(S)` : du JavaScript ES2017 qui DÉCLARE une scène animée. Tu ne dessines rien toi-même : tu crées des éléments, tu leur donnes des mouvements dans le temps, tu règles la caméra. Le runtime évalue tout à partir du temps `t` (rendu pur et déterministe).

## Format de sortie
Un seul bloc ```js contenant uniquement le corps de la fonction (pas de `function build`, pas d'`export`). Commentaires courts en français autorisés.

## Ce qui est autorisé (le reste est refusé par l'analyse statique)
- Variables `const`/`let`, boucles `for` (avec condition d'arrêt) et `for...of`, `if`, fonctions fléchées, `.map/.forEach/.slice/.join`, littéraux d'objets et de tableaux, gabarits `` `...` ``, opérateurs.
- Globales : `S`, `Math` (abs sin cos tan atan atan2 PI pow min max floor ceil round sqrt exp log sign hypot trunc — PAS `Math.random`), `hash(a,b)` (hasard déterministe entre 0 et 1), `W`=1080, `H`=1920, `Number`, `String`, `Array` (`Array.from({length: n}, (_, i) => i)`). Pas d'`Object` (utilise des tableaux), pas de `floor` seul : `Math.floor`.
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
- `box` : `w`(200), `h`(100), `corner`(16, rayon des coins ; `r` est la ROTATION en radians, 0 par défaut), `color`('panel'), `stroke`(''), `sw`(3). Centré.
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

## Gabarits de scène (`S.template(nom, params)`) — À PRÉFÉRER pour le contenu texte, maths, chiffres et processus
Compositions déjà dessinées : centrées, grandes, bien remplies, animées aux temps que TU donnes (secondes locales, souvent `S.t('ancre')`). Un élément prévu à `t <= 0.05` est visible dès la première image. Tu peux les combiner avec des éléments libres (`S.add`) et une caméra (`S.cam`) pour ajouter une illustration, un mot-clé, un mouvement. Un gabarit mal paramétré fait échouer le plan.
- `title` : `{text, sub?, t=0, color='ink', hide?}` — carte titre plein cadre avec particules.
- `equation` : `{lines:[{text, t, note?, color?}], size?}` — étapes empilées ; la ligne courante est vive, les précédentes s'estompent, la dernière est encadrée en vert. `note` = l'opération annoncée au-dessus de la ligne. Écris les maths en caractères simples (`2x + 3 = 11`, `−`, `÷`, `×`, `√`).
- `bignumber` : `{from, to, t0, t1, prefix?, suffix?, decimals?, label?, labelT?, color?}` — gros nombre qui compte de `from` à `to` entre `t0` et `t1`.
- `bars` : `{values, labels?, t0, t1, title?, readout?, readoutT?}` — histogramme plein cadre qui grandit.
- `linechart` : `{values, t0, t1, title?, xlabel?, ylabel?, ref?: {value, label}}` — axes + courbe tracée, droite de référence pointillée.
- `bullets` : `{items:[{text, t}], title?}` — cartes numérotées empilées, une par idée dite.
- `compare` : `{left:{title, items:[texte...], times?:[...]}, right:{...}, t?, step?}` — deux colonnes face à face.
- `flow` : `{nodes:[{label, t, color?}]}` — chaîne verticale de blocs reliés par des flèches (étapes d'un processus, trajet).
- `segment` : `{tCut, ratio=0.618, aLabel='a', bLabel='b'}` — segment coupé en deux parties (proportion, nombre d'or).
- `fibonacci` : `{t0, t1, n=8}` — pavage de carrés numérotés qui se construit (suite de Fibonacci).
Règle de choix : histoire vécue de messagerie ou de réseau (une personne qui envoie, reçoit, répond ; le trajet d'un message) → scène type `room` / `journey` ; contenu abstrait (calcul, chiffre, comparaison, liste, processus, géométrie) → gabarit ; scène vécue (personnage, lieu, appareil, trajet réel) → éléments libres (`house`, `person`, `phone`, `tower`, `water`...). Un plan peut mélanger les deux.

## Scènes types ILLUSTRÉES (`S.template`) — pour les histoires de messages, de téléphones et de réseaux
Séquences complètes extraites de la vidéo vitrine (décor plein cadre, personnage, caméra) : bien plus riches que ce que tu dessinerais à la main. Même appel que les gabarits ; un seul par plan en général.
- `room` : `{place:'dakar'|'paris', who:'awa'|'lea'|'malik'|'sam', tag?, contact?, message, typeFrom?, sendAt?, previous?, receiveAt?, reply?, replyFrom?, replyAt?, smileAt?, zoomPhone?:{t0,t1}, zoomOut?:{t0,t1}}` — une personne chez elle avec son téléphone, maison en coupe de nuit. `sendAt` : elle tape `message` puis l'envoie à cet instant (la bulle part, « Envoyé ✓ »). `receiveAt` : trois morceaux `#1 #2 #3` entrent par la fenêtre, le message se déchiffre sur son téléphone. `reply`/`replyAt` : elle répond. `smileAt` : elle sourit. `zoomPhone` : la caméra plonge dans l'écran du téléphone (raccord vers un plan d'interface). `tag` : mot-clé du lieu (« DAKAR »). La caméra fait un plan large puis s'approche d'elle toute seule.
- `journey` : `{t0?, dur?, label?, labels?}` — le trajet d'un message de bout en bout : antenne, câble qui plonge dans l'océan (poissons, baleine, bateaux), traversée, data center, antenne d'arrivée, avec trois paquets lumineux qui suivent le chemin et trois légendes. Il occupe `dur` secondes à partir de `t0` (par défaut tout le plan, ~22 s idéal ; plus court, il accélère). La caméra est gérée.
Un plan `room` ou `journey` ne demande presque rien de plus : ajoute au besoin un mot-clé (`hud: true`, 64 px) et des bruitages.

## Types et couleurs (vérifiés : une erreur fait échouer le plan)
Les nombres sont des nombres (`dark: 0.25`, jamais `true`), les booléens des booléens, `pid` un nombre. Une prop inconnue pour un élément (faute de frappe) est une erreur. Les couleurs sont un jeton de la liste ou `#rrggbb` : `'red'`, `'green'`… sont INVALIDES.

## Composition (ce qui sépare un plan moyen d'un plan de studio)
- Le sujet remplit le cadre : le contenu vit dans la zone y 250–1550 ; pas de grande zone vide (une image dont presque tout est du fond uni est refusée). Un décor (maison, ville, océan) est posé plein cadre, avec un sol qui descend jusqu'au bas de l'écran (`box` de grande taille, `layer: -1`).
- Maison : largeur 720 × `s`. Avec `s`=1,45 elle remplit l'écran. Personnage assis dans une maison de position (hx, hy) et d'échelle hs : `x = hx − 120·hs`, `y = hy − 106·hs`, `s = 1.25·hs` (`flip` : `x = hx + 110·hs`).
- Un seul décor par plan ; pour montrer deux lieux, deux plans (ou un déplacement de caméra), pas un écran coupé en deux.
- La caméra bouge toujours (zoom lent 1.0 → 1.15 minimum, ou travelling). Les mots-clés sont `hud: true`, 64 px minimum, placés en haut (y ≈ 230–330) ou en bas (y ≈ 1450–1550).
- Les éléments qui racontent (téléphone, paquets, chiffre) sont assez grands pour être lus sur un téléphone : au moins 90 px de haut.

## Règles de réalisation (elles seront vérifiées)
1. UN seul point focal à la fois. Pas d'image figée plus de 1,5 s : quelque chose bouge (caméra, apparition, pulse, particules).
2. Chaque phrase de la voix off fait bouger quelque chose de signifiant. Les actions importantes tombent sur leur ancre (`S.t`), à ±150 ms.
3. Aucun texte coupé par le bord de l'écran, aucun chevauchement de textes. Mots-clés ≥ 64 px, contraste fort, hors zones d'interface.
4. On doit comprendre le mécanisme sans le son.
5. N'invente AUCUN chiffre : n'affiche que ceux fournis par le plan.
6. Décor et personnages cohérents avec la bible (mêmes couleurs, mêmes props).
7. Le sujet principal est VISIBLE dès la première image (t = 0) : ne le fais pas apparaître avec `appear` après 0,1 s, un cadre vide au début tue l'accroche. Les éléments secondaires, eux, peuvent arriver ensuite.
7bis. Le plan doit s'exécuter vite (pas de boucles de milliers d'itérations).
8. Texte : si une ligne d'équation ou de légende risque de dépasser 900 px de large, donne `maxW: 860` à l'élément `text` (la taille se réduit pour tenir) : un texte coupé par le bord est une erreur.
9. Les tailles et dimensions animées restent positives : un easing `'back'` peut dépasser sous zéro, évite-le sur `w`, `h`, `rad`.
