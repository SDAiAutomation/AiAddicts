# Synchronisation voix / visuel : audit (2026-10-10)

Les sections 1 à 11 sont le constat de recherche (aucun code modifié à ce stade). La section 12 consigne les corrections appliquées ensuite et leur mesure. Les faits mesurés sont séparés des hypothèses.

## 1. Question et réponse courte

Le benchmark de référence avait signalé « 7 scènes sur 14 non synchronisées ». **Ce chiffre était faux et ne mesurait pas un défaut de timing.** Il comptait le drapeau interne `synced` du moteur (`False` pour toute scène sans liste d'éléments à caler : `big_number`, `icon_text`, `before_after`), pas un écart réel. Le décompte était en plus inexact : le drapeau vaut `False` pour 6 scènes sur 7 dans le cas 1 et 4 sur 7 dans le cas 4, soit 10 sur 14 et non 7. Une scène statique non calée n'est pas un défaut.

Mesure réelle sur les 5 vidéos du benchmark (31 scènes) : des écarts voix/visuel existent bel et bien, mais ils se concentrent dans **quatre mécanismes précis** (section 5). L'alignement audio/vidéo au niveau des clips et des sous-titres est exact.

## 2. Méthode et limites

- **Données** : MP4 réels et leurs clips silencieux par bloc, `audio/block-NN.words.json` (mots ElevenLabs, début/fin), durées audio (ffprobe), scripts. Cas 1 PocketLogic, 2 finance FR, 3 maths (Manim), 4 explainer, 5 récit cinétique (version actuelle, après les correctifs de la phase B).
- **Quand la voix dit un élément** : début du mot correspondant (égalité sur les chiffres normalisés, jetons numériques concaténés « 3 », « 000 » ; sinon mot significatif). Le début du premier mot a été recoupé avec l'énergie réelle de l'audio sur 20 blocs : écart moyen 0,08 s, maximum 0,14 s. Ce recoupement ne vérifie pas chaque mot.
- **Quand le visuel apparaît** : dans le MP4, instant où l'encre de la boîte mesurée par le moteur (recorder de preflight) atteint 50 % de sa valeur finale. Fondu d'entrée de 0,2 s : l'instant est jusqu'à ~0,1 s avant la pleine visibilité. Pour les compteurs animés : dernier instant où le chiffre change. Pour Manim : segments de mouvement (pixels qui changent).
- **Seuil d'alignement** : ±0,35 s (le moteur avance déjà les révélations de 0,12 s).
- **Lecture en temps réel : non effectuée.** Tout est jugé sur images échantillonnées à 25 fps et sur les métadonnées de timing. Je n'ai pas écouté l'audio. La fluidité et le ressenti ne sont pas évalués.
- **Faux positifs de ma propre méthode, écartés** : détection de coupe à 13,6 s au lieu de 13,08 s dans le cas 1 (le fondu d'entrée de la scène suivante est très sombre ; images à 13,0 / 13,1 vérifiées à la main) ; blocs Manim où l'audio est prolongé volontairement ; nombres dits en toutes lettres (maths) non comparables.
- Outils d'audit hors dépôt : `scratchpad/sync_audit/audit.py` et scripts de la session.

## 3. Alignement audio / clips / sous-titres (confirmé exact)

| Contrôle | Résultat |
|---|---|
| Durée du clip vs durée audio du bloc | écart ≤ 0,02 s sur 31 blocs, sauf bloc Manim 2 du cas 3 (clip 9,44 s, audio 7,99 s : prolongation voulue, l'audio est complété de silence, `math_steps.extra_hold_seconds` + `pad_audio`) |
| Coupes de scène dans la vidéo finale vs somme des durées | écart ≤ 0,04 s (cas 2, 4, 5) ; cas 1 et 3 : deux détections aberrantes expliquées ci-dessus |
| Flux audio vs flux vidéo (final) | cas 1 : 25,147 / 25,160 s ; cas 2 : 20,619 / 20,600 ; cas 3 : 26,633 / 26,640 ; cas 4 : 26,471 / 26,440 ; cas 5 : 21,618 / 21,640 ; écart maximal 0,03 s, pas de dérive cumulée |
| Sous-titres vs mots ElevenLabs (cas 2, 79 événements) | écart médian 2 ms, maximum 5 ms |

Conclusion : le montage (ffmpeg, concat, audio, sous-titres) n'est pas en cause.

## 4. Chronologie par scène (cas 1 et 4, les 14 scènes de la question)

Convention : « dit » = début du mot dans la voix ; « apparaît » = apparition visuelle dans le MP4 ; écart = apparaît − dit (négatif : le visuel précède la voix ; positif : le visuel est en retard). Tous les temps sont en secondes depuis le début du bloc.

**Cas 1, PocketLogic « 5 $ par jour »**

| Bloc | Scène | Narration | Élément | Dit | Apparaît | Écart | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | big_number | « $5 a day sounds small… » | « $5 » | 0,00 | 0,16 (compteur fini à 0,84) | +0,16 (fin +0,84) | compteur en retard de 0,84 s |
| 2 | icon_text | « …adds up to $1,825 a year » | « $1,825 A YEAR » | 1,47 | 0,52 | −0,95 | titre-chapeau, statique : choix de design, hors défaut |
| 3 | compound_growth | « …about $10,500 after five years, $25,200 after ten… » | « $10,500 » | 2,77 | 0,52 | **−2,26** | **défaut réel** (voir D2) |
| 3 | idem | | « $25,200 » | 5,05 | 4,64 | −0,41 | légèrement en avance |
| 4 | big_number | « After twenty years: about $74,800 » | « $74,800 » | 1,21 | débute 0,24, complet 1,56 | fin +0,35 | acceptable |
| 5 | before_after | « And you only put in $36,500… » | « $36,500 » | 0,81 | 0,32 | −0,49 | léger avance |
| 5 | idem | | « $74,800 » | non dit | 1,84 | n/a | contenu, pas timing |
| 6 | formula | « Time did about $38,300 of the work over those 20 years, not you. » | « + $38,300 GROWTH » | 0,69 | 1,80 | **+1,12** | **défaut réel** (voir D3) |
| 6 | idem | | « $36,500 YOU », « = $74,800 » | non dits | 0,80 / 2,80 | n/a | contenu : deux des trois lignes ne sont pas dans la narration |
| 7 | icon_text | « Where does your $5 a day go? » | texte | 0,50 | 0,28 | −0,22 | aligné |

**Cas 4, explainer « You Got a Raise »**

| Bloc | Scène | Narration | Élément | Dit | Apparaît | Écart | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | big_number | « You got a raise. So why are you still broke? » | « +$1,000 » | non dit | 0,20 (fini 1,08) | n/a | pas de comparaison possible |
| 2 | icon_text | « …pay goes up $1,000 a month. » | texte | 0,88 | 0,48 | −0,40 | acceptable |
| 3 | bar_chart | « …apartment adds $400. A car payment adds $300. Dining out adds $150. » | libellés | 0,56 / 2,35 / 4,11 | 0,48 / 2,28 / 4,04 | −0,07 | aligné |
| 3 | idem | | montants $400 / $300 / $150 | 1,20 / 3,11 / 4,97 | 0,48 / 2,28 / 4,04 | −0,72 / −0,83 / −0,93 | valeur en avance de 0,7 à 0,9 s (D4) |
| 4 | big_number | « That's $850 a month of new spending… » | « $850 » | 0,33 | débute 0,32, **complet 2,32** | fin **+2,00** | **défaut réel** (D1) |
| 5 | money_split | « So only $150 of your $1,000 raise is left over. » | « LEFT OVER $150 » | $150 à 0,58 | 2,84 | **+2,26** | **défaut réel** (D3) ; la première ligne « SPENT $850 » (jamais dite) apparaît à 1,4 |
| 6 | formula | « …Save half the raise before it lands: $500. » | « − $500 SAVED FIRST » | « Save » 2,45 ($500 à 4,12) | 2,40 | −0,05 par le mot, −1,72 par le chiffre | aligné par le sens (faux positif de la comparaison numérique) |
| 6 | idem | | « = $500 TO SPEND » | 4,12 | 4,04 | −0,08 | aligné |
| 7 | icon_text | « Money Rule #3 is next. » | texte | 0,58 | 0,24 | −0,34 | aligné |

**Cas 2 (finance FR)** : formule du bloc 5 alignée à ±0,04 s sur les trois termes, liste de contrôle du bloc 6 alignée à ±0,09 s (les deux sont des scènes calées sur la voix qui fonctionnent). Compteurs : « $3,000 » complet à 2,16 s pour une voix à 0,61 s (+1,55), « $600 » +1,09, « $2,400 » +0,78.

**Cas 3 (maths, Manim)** : le bloc 2 est correctement calé. Segments de mouvement : 2,56 à 2,96 (étape « On retire trois », dit à 2,54), 3,36 à 4,92 (résultat « 2x = 8 », dit 4,11 à 5,24), 6,00 à 8,00 (étape « on divise par deux », dit 6,00 ; « x égale quatre » dit 7,08 à 7,44). Écarts ≤ 0,3 s. Bloc 3 (graphe) : la droite se dessine pendant que la voix la décrit (1,12 à 2,64 pour « graphe de y égale deux x plus trois » dit 1,13 à 2,6) ; le point « x = 4, y = 11 » apparaît à ~3,5 s alors que « onze » est dit à 5,0 s (D7, mineur).

**Cas 5 (récit cinétique, version actuelle)** : voir D5, les 6 blocs sont en avance.

## 5. Défauts confirmés, causes et code

| # | Défaut | Mesure | Cause dans le code | Fréquence | Sévérité |
|---|---|---|---|---|---|
| D1 | **Compteur animé terminé après la voix** | fin du comptage en retard de 0,35 / 0,78 / 0,84 / 1,09 / 1,55 / 2,00 s (6 compteurs mesurables sur 7) | `scenes._big_value` : `count_up(t, …, start=0.05, end=0.55)`, fenêtre fixe en fraction de la durée du bloc. L'ancrage sur la voix (`_anchor`) n'existe que si le script porte `voiceAnchor` (`sync.attach_reveals`), or aucun des 7 scripts motion graphics n'en contient (seul `exemple-maths.json`) et le prompt amont ne le demande pas | tout `big_number` à chiffre animé | moyenne (le chiffre dit à 0,3 s se stabilise à 2,3 s) |
| D2 | **Fausse correspondance lexicale dans `compound_growth`** | « $10,500 » 2,26 s avant d'être dit, alors que la scène est marquée calée (`synced`) | `sync.compute_reveals` : les libellés « Year 5 / Year 10 » deviennent le jeton « year » (le chiffre « 5 » est écarté, longueur < 2), qui correspond par préfixe à « yearly » dit à 0,53 s | 1 scène calée sur 8 | élevée sur cette scène |
| D3 | **Valeurs d'une liste calées sur les libellés, pas sur les chiffres** | « $150 » 2,26 s après (money_split) ; « $38,300 » 1,12 s après (formula non calée) | `sync.item_texts` ne retient que les libellés (`data[].label`) ; les termes d'une formule contenant un montant ne correspondent jamais : `_tokens` coupe « $38,300 » en « 38 », « 300 » alors que les mots ElevenLabs donnent « 38300 » ; moins de la moitié des éléments reconnus fait retomber sur l'espacement régulier (`MIN_MATCH_RATIO`) | 2 scènes sur 14 | élevée (le chiffre clé est dit puis affiché 1 à 2 s plus tard) |
| D4 | **Valeur affichée avec son libellé, dite après** | 0,7 à 0,9 s | même mécanisme : un élément = libellé et valeur révélés ensemble au mot du libellé | bar_chart | faible |
| D5 | **Texte cinétique en avance de 1,3 à 3,05 s** | 6 blocs sur 6, moyenne 1,9 s | **régression que j'ai introduite** : le correctif de la phase B (`kinetic_typography.derive_emphasis_phrase`, commit `e5d1a31` publié) prend la fin de la phrase, mais la scène `icon_text` apparaît au début du bloc sans ancrage sur la voix. Avant ce correctif le texte (5 premiers mots) était aligné mais écrasé par les sous-titres | tous les blocs du style cinétique | élevée pour le récit (la fin de la phrase s'affiche avant d'être dite) |
| D7 | Point et coordonnées du graphe affichés ensemble | « y = 11 » visible 1,4 s avant « onze » | le marqueur et son libellé partagent la même animation | 1 scène | faible |

## 6. Faux positifs et cas à ne pas classer en défaut

- **Scènes statiques** (headline-first) : « $1,825 A YEAR » (−0,95), « EPARGNER EN DERNIER NE MARCHE PAS » (−1,04), titres de scène. C'est un choix éditorial (titre avant explication) ; il n'y a pas de défaut de timing. Aucune scène n'a été jugée fausse parce qu'elle est statique.
- **Drapeau `synced` = False** : sans objet pour les scènes à un seul élément.
- **Compteur partiel visible tôt** (« $14,443 » en cours de route) : voulu ; seul le moment où la valeur finale est atteinte compte.
- **Manim** : correct dans les trois étapes ; aucune action.
- **Écarts de −0,2 à −0,5 s** : dans la tolérance de la méthode.

## 7. Séparer précision de timing et qualité narrative

- **Précision de timing (défauts)** : D1, D2, D3, D5 (+ D4, D7 mineurs).
- **Qualité narrative / contenu** (hors timing, à ne pas corriger par la synchro) : lignes de formule du cas 1 non présentes dans la narration (« $36,500 », « = $74,800 »), ligne « SPENT $850 » jamais dite, doublon « +$1,000 » puis « RAISE: +$1,000 A MONTH ».

## 8. Correction minimale recommandée (non implémentée)

1. **D1 + D3 (même famille)** : dans `sync.py`, calculer les révélations à partir des **chiffres normalisés** des valeurs (`displayValue`, termes de formule) avant les libellés, et poser automatiquement l'ancre d'un `big_number` à son nombre dit (comme `voiceAnchor`, sans changer le schéma). Retombée : le compteur démarre au mot prononcé.
2. **D2** : conserver les jetons numériques d'un caractère dans `_tokens` pour les libellés, et exiger une correspondance non ambiguë (pas de préfixe sur un mot plus long).
3. **D5** : ancrer l'apparition du texte cinétique sur son premier mot dit (`words.json`, comme `_anchor`) ; repli : début du bloc.
Tout reste local au moteur ; pas de changement de schéma, de frontend ni de prompt.

## 9. Critères d'acceptation

- Sur les 5 vidéos de référence : tout élément à chiffre clé apparaît dans [−0,15 ; +0,35] s autour de son mot, compteur terminé inclus (≤ +0,5 s).
- Aucune scène aujourd'hui alignée (cas 2 blocs 5 et 6, Manim cas 3, bar_chart libellés) ne se dégrade (écart absolu maximal inchangé à 0,05 s près).
- Durées de clip, flux audio/vidéo et sous-titres strictement inchangés.
- Tests unitaires : `compute_reveals` sur des montants groupés (« $38,300 » vs « 38300 »), « Year 5 » vs « yearly », ancrage automatique d'un `big_number`, repli sans timestamps ; test de non-régression des scènes sans mots.
- Réévaluation avec le même outil d'audit sur les mêmes cas, comparaison avant/après.

## 10. Impact attendu sur rendu et coût

Aucun appel externe, aucun coût de génération. Le rendu des clips ne change pas de durée (mêmes images, instants d'apparition déplacés). Le calcul des révélations ajoute des comparaisons de chaînes négligeables. Aucune migration ; le cache de génération doit inclure `sync.py` (déjà listé dans le condensat) pour que les clips déjà rendus ne restent pas périmés.

## 11. Limites restantes

Écoute réelle et lecture en temps réel non faites ; le recoupement audio/mots ne porte que sur le premier mot de chaque bloc ; petit corpus (31 scènes, 5 vidéos) ; nombres dits en toutes lettres (maths) non mesurables par chiffres.

## 12. Corrections appliquées et mesure (mise à jour)

Publié sur `origin/growthos/mvp` : `f5e86aa` (D5) et `a8e1019` (D1 à D4). Aucun changement de schéma, de frontend, de prompt, de dépendance ni d'appel externe ; les 1 009 tests du moteur passent. Mesures refaites avec le même outil sur les mêmes cas, voix réutilisées.

| Défaut | Correction | Avant | Après |
|---|---|---|---|
| D5 texte cinétique en avance | `kinetic_typography.build_anchored_emphasis_scene` ancre le texte sur son premier mot dit ; `render_icon_text` n'affiche rien avant l'ancre | −1,31 à −3,05 s (6 blocs sur 6) | −0,04 à +0,04 s |
| D1 compteur terminé après la voix | `sync.attach_reveals` ancre un `big_number` sur son nombre dit (sans `voiceAnchor`) ; rien n'est dessiné avant | fin du comptage +0,35 à +2,0 s | +0,24 à +0,48 s |
| D2 fausse correspondance « Year 5 » / « yearly » | un élément qui porte un montant est calé sur ce montant | −2,26 s | −0,05 s |
| D3 montants groupés non reconnus | `digit_keys`, `item_numbers`, `number_index` : comparaison sur les chiffres, jetons « 3 » + « 000 » concaténés | +1,12 s (« $38,300 »), +2,26 s (« $150 ») | −0,05 s, −0,02 s |
| D4 valeur en avance sur son libellé | même règle : la valeur gouverne | −0,72 à −0,93 s | −0,07 à −0,09 s |
| D7 point et « y = 11 » du graphe en avance | non corrigé | −1,4 s | inchangé |

**Changements de comportement assumés.**
- Un chiffre n'est jamais affiché avant d'être dit. Les libellés d'une ligne qui porte un montant apparaissent donc avec le montant : libellés de barres jusqu'à 0,77 s après leur mot, « = $500 TO SPEND » 0,5 s après « $500 ».
- La formule « − $500 SAVED FIRST » (cas 4, bloc 6) passe de 2,4 s à 4,0 s, quand « $500 » est dit : alignée par le sens avant, par le chiffre maintenant.
- « LEFT OVER » (cas 4, bloc 5) s'affiche 2,3 s avant d'être prononcé, la ligne étant calée sur « $150 ».
- Une scène calée sur la voix ne dessine plus un élément avant sa révélation. Avant, le fondu parti de la couleur du fond laissait une ombre lisible du texte ou du montant ; avec des révélations tardives elle aurait duré jusqu'à 2,7 s.
- Un seul nombre reconnu suffit désormais pour caler une liste (au lieu d'exiger la moitié des éléments).

**Non modifié.** Durées de clip, coupes de scène (≤ 0,04 s), flux audio/vidéo, sous-titres (écart médian 2 ms) : mesurés identiques avant et après. Manim : inchangé.

**Limites.** Pas de lecture en temps réel ni d'écoute ; mesure sur images à 25 fps. Un chiffre dit en toutes lettres (maths) n'est pas reconnu. Deux lignes du cas 1 (formule) restent affichées sans être dans la narration : c'est un défaut de contenu (planification amont), pas de synchronisation. Deux durées de rendu mesurées (6 416 s et 410 s) sont faussées par la machine (suspension ou charge) et ne sont pas utilisables ; les autres rendus durent 122 à 162 s, comme avant.
