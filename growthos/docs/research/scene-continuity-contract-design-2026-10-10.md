# Continuité entre scènes : conception du contrat (2026-10-10)

Statut : conception uniquement. Aucun code de production, frontend, prompt LLM, dépendance, migration ni commit. Faits observés (code lu, mesures) séparés des hypothèses (H).

## 0. Verdict en une ligne

**NO-GO pour une implémentation en production maintenant.** Si on la veut quand même, la voie la moins coûteuse est l'approche B (métadonnée interne calculée par le moteur, sans changement de schéma, de frontend ni de prompt). Le blocage n'est pas technique : sous la règle « la voix d'abord », seulement 3 transitions sur 40 sont éligibles (section 5).

## 1. Architecture actuelle (constats, avec le code)

1. **Schéma** (`engine/motion_graphics/schema.py`) : `validate_scene` ne vérifie que la structure ; 15 `sceneType`. Les clés privées du moteur (`_reveals`, `_duration`, `_anchor`, `_solutionKind`, `_plan`, `_domainExclusions`) sont déjà un canal interne : `display_text._INTERNAL_FIELDS` les laisse passer jusqu'aux rendus, elles ne viennent jamais du script.
2. **Planification côté front** : `growthos-web/src/app/(app)/content/motion-graphics.ts` assainit chaque `motion_graphic` avec une liste blanche de clés (`title, text, label, displayValue, emphasis, voiceAnchor`, données…). Une nouvelle clé de scène serait supprimée tant que cette liste n'est pas modifiée, et le LLM ne la produirait pas sans changement de prompt (`ai-actions.ts`).
3. **Rendu** : chaque scène est une fonction pure `(data, t, thème, taille)` avec `t` de 0 à 1 sur la durée du bloc (`scenes.py`). Elle ne connaît ni la scène précédente ni la suivante. Chaque bloc donne un clip indépendant `motion-NN.mp4`, rendu séparément (`renderer.render_scene_clip`).
4. **Assemblage** (`engine/video.py`) : `plan_shots` découpe un bloc en plans courts sans changer sa durée ; chaque plan est ré-encodé (`_render_block_clip`) puis concaténé par le demuxer concat (coupes franches, `fade_duration` 0 par défaut). Il n'y a pas de composition entre clips.
5. **Timings de narration** : `audio/block-NN.words.json` (mots écrits, ex. « $74,800. ») lu par `sync.attach_reveals`. Il fournit `_reveals` (une valeur normalisée par élément de liste) et `_anchor` (`big_number` avec `voiceAnchor`). Seuls `timeline`, `checklist`, `formula`, `money_split`, `bar_chart`, `donut_chart`, `compound_growth`, `comparison` ont des éléments synchronisés ; `before_after` n'en a pas.
6. **Preflight** (`preflight.check_scene`) : rend la scène à `t = 1.0` avec le recorder de boîtes (`layout.record_boxes`) et rejette chevauchements, sortie de cadre, zone des sous-titres. Il ne regarde que l'image finale, pas les instants intermédiaires.
7. **Cache** : `generation_cache.fingerprint` = script complet + voix + code des modules listés. Un clip n'est réutilisé que dans un même dossier de travail (`_exists_nonempty`). Le script entier est haché, donc les scènes voisines sont déjà dans l'empreinte ; les timings de mots dépendent du texte et de la voix, donc aussi couverts.
8. **Plus petit point d'introduction** : `visuals.fetch_motion_graphics_clips` → `prepare_motion_graphics_scene` (par bloc, avant rendu). C'est là que `_reveals` est posé aujourd'hui, et le seul endroit qui voit à la fois la scène, les mots et la durée. Limite : il traite un bloc à la fois ; la continuité demande une seconde passe qui voit deux blocs voisins.

## 2. Comparaison des approches

| | A. Dériver des scènes voisines (sans stockage) | B. Métadonnée interne de rendu (`_carry_in`) | C. Contrat explicite dans le schéma |
|---|---|---|---|
| Idée | à chaque rendu, comparer les valeurs des scènes i et i+1 | même dérivation, mais matérialisée une fois en champ privé comme `_reveals` | le LLM/front déclare la liaison dans `motion_graphic` |
| Changement front / prompt | non | non | oui (liste blanche TS + prompt + type) |
| Déterminisme et test | oui, mais logique dispersée | oui, une fonction pure testable, résultat dans le rapport | dépend de la sortie LLM (liaisons inventées) |
| Identité sémantique | devinée par égalité de valeur | idem, avec garde-fous explicites | portée par l'auteur de la scène (plus fiable) |
| Risque | recalcul dans chaque rendu, difficile à auditer | passe supplémentaire à créer dans `visuals.py` | scripts existants sans contrat, hallucinations, migration des brouillons |
| Migration | aucune | aucune (clé privée absente = comportement actuel) | champs optionnels, mais prompt et validation à versionner |

Recommandation si on construit : **B**, avec la dérivation de A. **C** seulement plus tard, comme surcharge optionnelle validée par le moteur, si l'ambiguïté sémantique de B s'avère insoutenable.

## 3. Contrat minimal recommandé (interne, version 1)

Posé sur la scène de destination par le moteur, jamais écrit dans le script ni en base. Ne duplique rien : valeur, libellé et rôle viennent des champs existants.

```json
{
  "_carry_in": {
    "v": 1,
    "id": "number:74800:b4>b5",
    "kind": "number",
    "value": {"display": "$74,800", "normalized": "74800", "unit": "currency"},
    "source": {"block": 4, "ref": "displayValue",
               "box": [115, 842, 965, 1033], "fontPx": 211, "color": "#F8FAFC"},
    "dest":   {"block": 5, "ref": "after.displayValue",
               "box": [308, 986, 770, 1091], "fontPx": 105, "color": "#22C55E"},
    "handoff": {"durationSec": 0.45, "ease": "out_cubic"},
    "gate": {"destRevealSec": 0.3, "maxDelaySec": 0.6,
             "narratedInDest": true, "firstNumberInDest": true},
    "fallback": "cut"
  }
}
```

- `kind` : `number` en v1. `text`, `chart`, `expression` sont réservés, avec le même squelette (identité, source/destination, boîtes). Pas de cadre d'animation générique.
- `id` stable : type + valeur normalisée + paire de blocs.
- Géométrie mesurée, pas déclarée : les boîtes viennent du recorder de preflight (déjà là), en pixels sur le canevas de référence 1080x1920.
- Le champ `source` sert au rapport et aux tests ; seule la destination dessine.

## 4. Exemple de rapport (`motion_preflight`)

```json
{"blockIndex": 4, "sceneType": "before_after", "synced": false, "action": "none",
 "carry": {"status": "dropped", "reason": "dest_reveal_after_max_delay", "destRevealSec": 2.2}}
```
Sur le cas d'école du prototype (PocketLogic « 5 $ par jour », blocs 4 vers 5), le contrat serait refusé : voir section 5.

## 5. Synchronisation « la voix d'abord »

**Principe** : un élément reporté ne peut occuper sa place d'arrivée que si la voix le nomme à ce moment-là. Donc l'élément n'est éligible que si son ancrage de révélation dans la scène de destination est précoce (`maxDelaySec`, 0,6 s par défaut) ; sinon, coupe franche. Le prototype D a justement échoué sur ce point.

Règles de décision, par défaut « refuser » :

| Cas | Comportement |
|---|---|
| Valeur répétée à l'identique, 1ère valeur citée de la destination | éligible |
| Valeur reformatée (« 74 800 » / « 74,800 » / « $74.800 ») | égalité sur les chiffres normalisés **et** même unité (devise, pourcentage) ; sinon refus |
| Plusieurs nombres dans la narration | éligible seulement si le nombre reporté est le premier cité, ou si son ancrage est ≤ `maxDelaySec` |
| Valeur absente de la narration de la destination | refus (rien ne l'autorise à apparaître) |
| Timings de mots absents ou non fiables (pas de `words.json`, correspondance faible) | refus |
| Même nombre, sens différent (« 1 000 $ de hausse » puis « 1 000 $ de fonds d'urgence ») | refus si les libellés des deux éléments ne partagent aucun mot significatif ; défaut = refus |
| Bloc de destination court (< 1,2 s), bloc `reuse_visual_from_previous`, quiz, Manim | refus |

Ancrages : mots de `words.json` comparés par égalité de chiffres normalisés (les mots sont déjà en forme écrite, ex. « $36,500. »), avec le décalage `LEAD_SECONDS` de `sync.py`. Les nombres écrits en toutes lettres ne sont pas gérés (refus).

**Mesure sur le dépôt (faits)** : 7 scripts motion graphics (5 PocketLogic, 1 finance FR, 1 exemple), 40 transitions de scènes adjacentes.
- 10 ont une valeur numérique répétée (25 %).
- Dans 3 seulement, cette valeur est le premier nombre cité dans la narration de la destination (PocketLogic 01 blocs 4→5 « 1000 », 02 blocs 1→2 « 1000 », 05 blocs 5→6 « 10000 ») : **3 sur 40, soit 7,5 %**.
- Dans 5 des 10, la valeur répétée n'est pas dite dans la scène de destination du tout (dont le cas d'école 04 blocs 4→5, « 74 800 ») : refus.
Limites : petit corpus, extraction par expression régulière, vérification sur le texte et non sur les timestamps de mots.

## 6. Propriété et superposition de l'élément en transit

Défauts du prototype D : double rendu, chevauchement, révélation prématurée, placement non sûr.

- **Un seul propriétaire : la scène de destination.** Son rendu dessine l'élément avec un seul appel, à la place de son dessin natif, avec une progression `p(t)` de 0 à 1 sur `handoff.durationSec`. À `p = 0` il occupe exactement la géométrie de la dernière image de la scène source ; à `p = 1` son rendu est identique au dessin natif (test pixel à pixel). Il n'y a jamais deux copies.
- **La scène source n'est pas modifiée** : son image finale contient déjà l'élément à la boîte mesurée. La coupe franche entre clips devient invisible pour cet élément, sans composition entre clips (compatible avec le concat et le découpage `plan_shots`).
- **Ordre de dessin** : l'élément en transit est dessiné en dernier pendant le transfert. Les autres éléments de la destination suivent leurs propres révélations (`_reveals`) et ne sont jamais avancés.
- **Zones sûres** : les deux positions sont dans la zone de contenu, qui est un bandeau convexe, donc la trajectoire rectiligne y reste. Le preflight est étendu : même rendu `check_scene` à `t` = 0, 25 %, 50 %, 100 % de la durée du transfert ; une erreur (chevauchement, sortie de cadre, zone des sous-titres) abandonne le contrat et garde la coupe.
- **Collision avec un élément déjà révélé** : la trajectoire ne doit pas croiser la boîte d'un élément dont la révélation est antérieure à la fin du transfert, sinon abandon.

## 7. Applicabilité (conservatrice, opt-in)

Drapeau d'environnement `MOTION_CARRY` (défaut désactivé), puis activation par type de scène et de niche une fois l'éligibilité prouvée.

| Domaine | Applicable en v1 ? |
|---|---|
| Finance personnelle | oui (valeurs répétées), mais éligibilité mesurée 7,5 % |
| Visualisation de données | `kind: chart` réservé, non fait en v1 |
| Équations | non : la transformation d'une étape à l'autre existe déjà dans la scène Manim ; Manim tourne en sous-processus, hors de cette passe |
| Explicatif éducatif | rarement (peu de valeurs répétées) |
| Récit | non (pas de valeurs ; typographie cinétique séparée) |

## 8. Validation et repli

Contrat abandonné (coupe franche) pour tout motif ci-dessus, avec la raison dans `motion_preflight[].carry`. Aucune exception ne doit sortir (même philosophie « jamais bloquant » que `_sync_and_preflight`). Drapeau désactivé : comportement actuel, octet pour octet.

## 9. Modules concernés (si go)

- Nouveau : `engine/motion_graphics/carry.py` (éligibilité, contrat, ancrages).
- `engine/visuals.py` : seconde passe dans `fetch_motion_graphics_clips` (aujourd'hui un bloc à la fois) ; `prepare_motion_graphics_scene` reste inchangé pour la partie existante.
- `engine/motion_graphics/scenes.py` : dessin « sensible au transfert » pour `big_number`, `before_after` (et `formula`) via un petit assistant partagé.
- `engine/motion_graphics/display_text.py` : `_INTERNAL_FIELDS` + `_carry_in`.
- `engine/motion_graphics/preflight.py` : échantillonnage du transfert.
- `engine/motion_graphics/sync.py` : exposer la recherche d'un nombre dans les mots (réutilise le tokenizer existant).
- `engine/generation_cache.py` : ajouter le module au condensat.
- `engine/motion_graphics/preview.py` : l'aperçu isolé n'a pas de voisin ; rester sans transfert.
- Inchangés : frontend, prompts, `schema.validate_scene`, base de données, assemblage `video.py`.

## 10. Compatibilité ascendante

Clé privée absente = rendu identique (test de non-régression par hachage d'images échantillonnées sur les scripts existants). Aucun script, aucune ligne en base, aucune migration. Les anciennes versions du moteur ignorent la clé. Le rapport s'enrichit d'un champ additif.

## 11. Plan de tests et de benchmark

- Unitaires : table des cas de la section 5 (verbatim, reformaté, plusieurs nombres, absent, mots manquants, même nombre / sens différent) ; unités ; seuils.
- Rendu : à `p = 1`, image identique à la scène native ; à `p = 0`, boîte égale à celle de la dernière image de la source (tolérance d'un pixel) ; hachage inchangé pour les scènes sans contrat.
- Preflight : transferts qui chevauchent, sortent du cadre ou entrent dans les sous-titres sont abandonnés.
- Audit d'éligibilité reproductible (le script ci-dessus) sur tout nouveau corpus, avec critère de décision.
- Benchmark visuel : paires éligibles uniquement (PocketLogic 01 blocs 4→5, 02 blocs 1→2, 05 blocs 5→6), avant/après sur images et lecture, avec mêmes durées et mêmes sous-titres.

## 12. Complexité estimée

Moyenne : environ 400 à 600 lignes de moteur et autant de tests. Le risque principal est la seconde passe dans `visuals.py` (l'API actuelle est bloc par bloc), pas le dessin. Estimation de l'ordre de quelques jours d'ingénierie ; je ne l'ai pas chiffrée au-delà.

## 13. Recommandation

**NO-GO maintenant.** Raisons :
1. Éligibilité mesurée de 7,5 % des transitions sous la règle « la voix d'abord ».
2. Le cas qui avait justifié le prototype est inéligible (valeur non dite dans la scène de destination).
3. Le gain visuel de la variante D n'a été vu que sur images fixes.

Réévaluer si, sur au moins 30 scripts réels, plus de 20 % des transitions deviennent éligibles (par exemple si la planification amont ordonne les valeurs répétées en tête de narration, ce qui touche aux prompts et reste hors de ce lot). Dans ce cas, démarrer par l'approche B derrière `MOTION_CARRY`, limitée à `kind: number`.
