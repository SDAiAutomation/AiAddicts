# Explainer animé — plan de la phase 0

Statut : **plan à valider, aucun code écrit.** Rédigé le 2026-10-15 après lecture de `PRODUCT_DOCTRINE.md`, `AGENTS.md`, `engine/motion_graphics/*`, `engine/tts.py`, `engine/assembler.py` (blocs voix/visuels), `engine/video.py`, `engine/captions.py`, `engine/generation_cache.py`, `scripts/queue_needs_manim.py`, `.github/workflows/growthos-worker.yml`, `growthos-web/docs/design-system.md` et du prototype `voyage-message.html` + `render.py`.

## 1. Le constat de départ : ce qui est confirmé, ce qui est corrigé

| Affirmation du brief | Verdict | Détail |
|---|---|---|
| 15 types de scène figés dans `schema.py` | Confirmé | `SCENE_TYPES` en compte 15. |
| Un clip isolé par bloc de voix off | Confirmé | `visuals.fetch_motion_graphics_clips` rend `images/motion-NN.mp4` par bloc, puis `video.render_final` concatène. |
| Dessin Pillow, suréchantillonné | Confirmé | `canvas.py`, `renderer.py`, `scenes.py`. |
| Manim : 60–250 s par scène, timeout 900 s | Timeout confirmé (`MANIM_TIMEOUT_SECONDS`, 900). Les 60–250 s viennent de mesures antérieures, non revérifiées ici. | |
| Timings au mot déjà produits | Confirmé | `audio/block-NN.words.json`, `tts.synthesize_with_timestamps`. **Mais ils sont relatifs au début de chaque bloc** : il faudra construire la timeline globale avec les décalages des blocs, y compris `hold_after_seconds` et le silence ajouté à l'audio pour les épisodes de maths. |
| `math_validation.py` et `math_steps.py` dans `engine/` | **Corrigé** | Ils sont dans `engine/motion_graphics/`. |
| Workflow dans `.github/workflows/` du dépôt `growthos` | **Corrigé** | Le dépôt git est `AiAddicts` ; le workflow est à sa racine (`.github/workflows/growthos-worker.yml`) et fait `working-directory: growthos`. |
| `scripts/queue_needs_manim.py` comme modèle | Confirmé | Même mécanique pour `queue_needs_explainer.py`. Il n'écrit jamais d'erreur bloquante. |
| Sous-titres coupables via `CAPTIONS_OFF = "off"` | Confirmé | `captions.py:26`. En mode `off` les marges de sécurité des sous-titres ne servent plus. |
| Constantes `SAFE_BOTTOM_RATIO` / `CAPTION_RESERVED_RATIO` | Confirmé | `SAFE_BOTTOM_RATIO = 0.42`, `SAFE_TOP_RATIO = 0.09` dans `motion_graphics/canvas.py` ; `CAPTION_RESERVED_RATIO` est un alias dans `layout.py`. |
| Polices OFL embarquées « comme Poppins » | Confirmé en partie | `assets/fonts` contient Poppins, IBM Plex Sans, Nunito. **Bricolage Grotesque et JetBrains Mono (utilisées par le prototype) n'y sont pas** : à ajouter, avec leur licence OFL. |
| Thème : `src/lib/motion-theme.ts` + `theme.py` | `theme.py` confirmé (7 palettes, `THEME_VERSION`). Le fichier web n'a pas été relu en phase 0. | |
| Worker `ubuntu-latest`, `timeout-minutes: 45` | Confirmé | Dépôt public, minutes Actions illimitées. Un passage traite la file en série. |
| Playwright disponible | **Non** côté moteur | `requirements.txt` ne contient ni Playwright ni Chromium. Côté web, `@playwright/test` est une dépendance de dev. À ajouter (voir §6, R1). |
| `render.py` du prototype | **Non réutilisable tel quel** | Chemin Chromium en dur (`/opt/pw-browsers/chromium-1194/...`), polices dans un dossier `gf/`, rendu en JPEG 0,95 via `toDataURL`. À réécrire proprement (§3.6). |

### Deux points qui contredisent le brief

1. **Aucun appel à un modèle Anthropic n'existe dans le code.** Le script est généré par OpenAI (`gpt-5-mini`, `OPENAI_SCRIPT_MODEL`) côté web ; le moteur Python appelle OpenAI pour l'originalité et la qualité. Le brief demande « Claude Opus » pour le réalisateur, l'animateur et le critique avec vision. **L'utilisateur a décidé le 2026-10-10 de ne pas payer d'API Anthropic en plus et de ne pas brancher de critique automatique au pipeline.** Cela touche directement les phases 3 et 4 (question Q1).
2. **L'exécution par plan crée un nouvel état de job.** Aujourd'hui le script (blocs de texte) est écrit côté web puis le worker fait voix → visuels → montage d'un seul trait. Les ancres du storyboard dépendent des timings de la voix, qui n'existent qu'après la synthèse. Le réalisateur doit donc tourner **dans le worker, après la voix**, et l'étape « valider le storyboard avant le rendu complet » (§5 du brief) impose un statut d'attente intermédiaire (§4.3).

## 2. Architecture

Nouveau paquet `engine/explainer/` à côté de `motion_graphics/`, sans rien y modifier. Seuls points de contact :

- `visuals.py` : un nouveau préfixe de style (comme `prefers_motion_graphics`) route vers l'Explainer.
- `assembler.py` : un embranchement dans le bloc « visuels » (là où `motion_graphics_style` est traité aujourd'hui) ; la voix, les sous-titres, le mixage et le rapport de coût restent ceux de l'existant.
- `generation_cache.py` : ajouter les modules du paquet à `_GENERATION_MODULES` pour que le cache d'actifs s'invalide quand le runtime change.
- Reprise de `motion_graphics/sync.py` (appariement tolérant, élisions, nombres en lettres via `word_value`, `number_index`) **par import**, pas par copie.

```
engine/explainer/
  runtime/        JS figé, versionné (RUNTIME_VERSION)
  director.py     sujet + script + timeline de mots -> storyboard
  animator.py     storyboard d'un plan -> code JS contre l'API du runtime
  validate.py     AST (liste blanche) + essai Chromium + sondes + déterminisme
  critic.py       planche d'images clés -> notes (phase 4, voir Q1)
  render.py       Playwright + ffmpeg (réécrit)
  timeline.py     blocs + words.json -> timeline globale de mots, résolution des ancres
  schema.py       storyboard + rapport (validation de structure, jamais bloquante)
  report.py       explainer.report.json
  reference/      voyage-message.html (golden), plans de référence
```

### 2.1 Pourquoi le JS ne tourne jamais hors de Chromium
Le code de l'animateur est du texte. Il n'est jamais `exec`/`eval` en Python ni Node. Il est chargé dans une page Chromium **par plan** : réseau coupé (`page.route` n'autorise que `file:` ; le runtime est servi en `file:`), pas de disque en écriture, un watchdog **processus** (pas seulement un timeout d'évaluation : une boucle infinie bloque le thread de la page). Aucun secret n'entre dans la page ; les clés restent en variables d'environnement Python.

## 3. API du runtime (signatures proposées)

Principe : le LLM n'écrit **que** `plan(ctx)` qui retourne des déclarations ; il n'a pas accès au canvas. Cela rend `renderAt` pur par construction et simplifie la liste blanche AST.

### 3.1 Cœur (`core.js`)
```js
const P = Faceloop.plan({ id, duration, world })        // un plan
P.at(t, fn)                                             // action à l'instant t (secondes du plan)
P.on(anchorId, fn)                                      // action à l'instant résolu d'une ancre texte
P.camera.keys([[t, {x,y,z,rot,focus}, ease?], ...])     // caméra 2.5D
P.layer(name, depth)                                    // calque parallaxe
P.transition(kind, {at, duration})                      // 'zoomThrough' | 'cut' | 'wipe' | 'dip'
Faceloop.ease.{io,out,inn,back}   Faceloop.kf(t, keys)  // easings et keyframes
Faceloop.hash(a, b)                                     // hasard seedé (Math.random interdit)
// hôte : renderAt(t) -> void, VIDEO = {duration, fps, plans, sfx}
```

### 3.2 Éléments animables (communs à tous les kits)
Chaque objet créé par un kit retourne un handle avec les mêmes verbes :
`appear(t, {from})`, `move(t0, t1, to, ease)`, `pulse(t)`, `highlight(t0, t1)`, `explode(t)`, `morph(t0, t1, to)`, `hide(t)`.

### 3.3 `kit-world.js` / `kit-tech.js`
```js
world.house({x, y, cutaway:true, city:'Dakar'})  world.street(...)  world.cityNight(...)
world.ocean({depth, cables:[...]})  world.globe(...)  world.dataCenter(...)  world.sky({time})
world.person({id, skin, hair, outfit, accessory, x, y})   // identité = fiche du storyboard
  person.pose(t, 'stand'|'sit'|'typing'|'turnHead'|'surprised'|'happy')
tech.phone({ui:'chat', text})  tech.laptop()  tech.antenna()  tech.router()  tech.satellite()
tech.packet({label, color})   tech.flow(path, {packets})  tech.envelope()
```
UI de messagerie générique, aucune marque.

### 3.4 `kit-math.js` (phase 5)
```js
math.eq(id, latex)   math.morph(t0, t1, fromId, toId, {applied:'−3 des deux côtés'})
math.axes(...)  math.plot(fn, {from, to, draw:[t0,t1]})  math.shape(...)  math.vector(...)
```
KaTeX servi localement. La justesse reste vérifiée **en amont** par `motion_graphics/math_validation.py` sur les étapes que le réalisateur reçoit ; le runtime ne calcule rien.

### 3.5 `type.js`, `fx.js`, `audio.js`, `probe.js`
```js
type.keyword(t, 'sept couches', {size>=64, at:'focus'})   type.counter(t0, t1, from, to)
fx.glow/trail/particles/grain/vignette/blur
audio.sfx(t, 'whoosh'|'pop'|...)  audio.music(trackId, {duck:true})
probe.report() -> {offscreen, overflow, overlaps, safeZoneViolations, errors}
```
La règle existante du moteur « un chiffre ne s'affiche jamais avant d'être dit » (`sync.py`) devient une **sonde** : un `type.counter` ou un nombre dont l'apparition précède son ancre vocale est une erreur de validation.

### 3.6 Rendu (`render.py`)
Playwright (Chromium résolu par Playwright, plus de chemin en dur), polices locales via `@font-face` `file:`, `renderAt(t)` image par image. Capture : PNG pour le golden, JPEG qualité 0,95 pour la production (comme le prototype) ou CDP `Page.screencast`/`captureScreenshot` si le coût de `toDataURL` est mesuré comme goulot en phase 1. Découpage par plans, rendu en parallèle sur plusieurs pages, ffmpeg `libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart`. Cache par plan : clé = hash(code du plan, storyboard du plan, thème, `RUNTIME_VERSION`, version Chromium), via `asset_store`.

## 4. Schéma du storyboard et intégration au pipeline

### 4.1 Storyboard (JSON, `schema.py`)
```json
{
  "version": "explainer-storyboard:v1",
  "truthMode": "fact" | "inspired" | "fiction",
  "world": { "metaphor": "...", "locations": ["house-dakar", "ocean", "datacenter", "flat-paris"] },
  "bible": {
    "characters": [{ "id": "awa", "skin": "...", "hair": "...", "outfit": "...", "accessory": "..." }],
    "objects": [{ "id": "phone-a", "kind": "phone" }]
  },
  "plans": [{
    "id": "p03", "intent": "le message devient des morceaux",
    "set": "house-dakar", "present": ["awa", "phone-a"],
    "camera": [{ "t": 0, "x": 0, "y": 0, "z": 1 }],
    "actions": [{ "id": "a1", "verb": "move", "target": "phone-a", "anchor": { "text": "découpé", "occurrence": 1 } }],
    "keywords": [{ "text": "morceaux", "anchor": { "text": "morceaux" } }],
    "sfx": [{ "type": "split", "anchor": { "text": "découpé" } }],
    "transitionOut": "zoomThrough",
    "claims": [{ "text": "...", "kind": "mechanism" | "figure", "source": null }]
  }]
}
```
`claims` porte les affirmations factuelles pour le contrôle de vérité (§4 du brief) : pas de chiffre sans source, sinon reformulation sans chiffre. `source` reste `null` plutôt qu'inventé.

### 4.2 Timeline globale et ancres (`timeline.py`)
Entrée : `blocks[]`, `audio/block-NN.words.json`, durées de blocs (y compris silences ajoutés). Sortie : liste unique de mots avec temps absolus. Résolution d'une ancre : recherche du mot (occurrence n) avec les fonctions de `sync.py`. Ancre non résolue → l'action reste, calée sur le début de la phrase, et le rapport l'écrit (jamais de plan perdu pour une ancre manquante).

### 4.3 Flux de job
Aujourd'hui : `queued → generating → (quality_check) → done`. Proposition :
1. `queued` : voix (cache d'actifs `voice`), timeline globale.
2. **Réalisation** : le réalisateur produit le storyboard, validé par `schema.py`, enregistré dans le script (clé dérivée comme `retentionDiagnostics`, donc exclue de `fingerprint` pour ne pas invalider le cache vocal).
3. **Option A (par défaut proposé)** : le job s'arrête en `awaiting_storyboard_review` ; le web affiche les plans ; l'utilisateur valide ; un second passage du worker anime, valide, rend. **Option B** : tout enchaîné sans pause (comme aujourd'hui), validation éventuelle seulement par un « régénérer ce plan » après coup. À trancher (Q4) : A respecte le brief mais ajoute un statut et une migration `content_items` ; B ne change pas le modèle de statuts.
4. Animation → validation → (critique) → rendu → montage final (voix + musique + SFX, sous-titres `off` par défaut).

Le repli par plan (R5) rend la scène `motion_graphics` Pillow équivalente **pour ce passage**, avec une entrée explicite dans `explainer.report.json` ; jamais silencieux.

## 5. Estimation de coût et de temps (estimations, à mesurer)

Hypothèse de travail : vidéo de 60 s, ~8 plans, jusqu'à 2 itérations de correction.

| Étape | Volume estimé | Remarque |
|---|---|---|
| Réalisateur | ~15 k tokens in / ~5 k out | 1 appel |
| Animateur | 8 plans × (~12 k in avec doc + 2 plans de référence, ~3 k out), × jusqu'à 3 passes | worst case ≈ 290 k in / 72 k out |
| Critique vision (si activée) | 8 planches × ~3 k in, jusqu'à 2 tours | ≈ 50 k in |
| **Total LLM, pire cas** | **≈ 350 k in / ≈ 90 k out** | |
| Voix ElevenLabs | ~900–1 100 caractères | à 0,18 $/1 000 caractères (variable du workflow) ≈ 0,16–0,20 $ |
| Rendu | 60 s × 30 fps = 1 800 images | cible < 5 min ; le prototype fait < 2 min mais sans critique ni plusieurs pages |

Prix : seul le tarif OpenAI configuré dans le workflow est connu (`gpt-5-mini` : 0,25 / 2 $ par million de tokens). À ce tarif le pire cas ≈ 0,09 + 0,18 ≈ **0,27 $**. **Le tarif d'un modèle Claude n'est pas dans le dépôt : coût Claude = inconnu**, à renseigner avant la phase 3. Coût mesuré aujourd'hui d'une vidéo standard : ~0,34–0,37 $ (mémoire du 25/09), donc l'Explainer ne tient pas la marge Pro (quota 40) si l'animateur est un gros modèle cher sans plafond. D'où un budget de tokens/coût par vidéo et une revue explicite au-delà (doctrine : tentatives bornées par essais et coût).

## 6. Risques

| # | Risque | Mitigation |
|---|---|---|
| R1 | **Chromium dans le worker** : ~150–300 Mo, `playwright install --with-deps chromium` ajoute du temps ; le job a 45 min et traite la file en série. | Étape conditionnelle (`queue_needs_explainer.py`), cache `~/.cache/ms-playwright`, mesurer le surcoût réel en phase 1. |
| R2 | **Qualité du code généré par un modèle moins fort** (Q1) : l'animateur est la partie la plus exigeante du projet. | Runtime riche (le LLM assemble, ne dessine pas), 2–3 plans de référence, validation stricte, repli Pillow. Banc de 5 sujets avant toute promesse. |
| R3 | **Déterminisme** : polices (métriques), `ctx.letterSpacing` selon la version de Chromium, `OfflineAudioContext`. | Version de Chromium épinglée et écrite au rapport ; golden comparé avec tolérance perceptuelle, pas au hash octet près, sauf test « deux rendus de même `t` ». |
| R4 | **Sécurité du code généré** : AST insuffisant (`constructor`, accès dynamique, `Function`). | Liste blanche d'identifiants et de nœuds, interdiction de l'accès computed sur les globales, réseau coupé, watchdog processus, exécution isolée par plan. L'AST réduit le risque, le bac à sable le borne. |
| R5 | **Repli Pillow incohérent** avec le monde visuel de la vidéo. | Écrit au rapport ; accepté comme dégradation visible plutôt que plan manquant. |
| R6 | **Synchronisation ±150 ms** : les sous-titres coupés ôtent tout filet de sécurité ; ElevenLabs alignement par caractère donne des mots, pas des phonèmes. | Ancres sur mots entiers ; sonde de tolérance dans `probe.js` ; vérification sur le banc. |
| R7 | **Droits musique/polices** (« musique libre de droits » exigée). | Pas de fichier ajouté sans licence écrite dans le dépôt ; sinon musique générée (Eleven Music est déjà utilisé dans AutoEdit : `autoedit_music.py`) ou aucune musique en première version. |
| R8 | **Surface de changement large** (moteur + web + migration + workflow). | Phases, une PR par phase, tests à chaque phase. Rien ne touche Pillow, Manim ou les autres styles. |
| R9 | **Vidéo vitrine écrite à la main (phase 2)** : gros chantier d'illustration (personnages, maison en coupe, océan en coupe, data center) en canvas 2D. | C'est le vrai test du kit ; prévoir plusieurs aller-retours visuels avec l'utilisateur. |
| R10 | **Vérification visuelle** : build/tests verts n'attrapent pas les défauts de rendu. | Planches de contact ffmpeg regardées en séance + captures Playwright du web à 390 px ; les dire explicitement quand elles manquent. |
| R11 | **Doctrine** : le contenu factuel (câbles sous-marins, chiffres) ne doit rien inventer. | `claims[]` obligatoire, pas de pourcentage non sourcé, mode vérité persisté. |

## 7. Plan de phases, ajusté

Je conserve les phases 0 à 6 du brief. Ajustements proposés :

- **Phase 1** : ajouter la mesure du coût d'installation de Chromium sur le worker et le choix de capture (`toDataURL` vs CDP) *avant* d'optimiser. Acceptation inchangée (MP4 équivalent au prototype, déterministe, < 3 min).
- **Phase 3** : le critère « 5 vidéos rendues sans intervention, moyenne ≥ 4 » dépend de Q1 (modèle de l'animateur) ; je propose de fixer ce critère *après* un essai de 1 sujet avec chaque modèle candidat.
- **Phase 4** : à ne démarrer que si Q1 autorise un critique ; sinon remplacée par des planches de contact examinées en séance (comme décidé le 10/10).
- **Phase 5** : le brief demande de comparer à Manim sur les épisodes maths existants ; je compare aussi le coût de maintenance (Manim + LaTeX ≈ 2 min d'installation à chaque passage qui contient des maths).
- **Phase 6** : la partie web est la mienne (consigne du 2026-10-03). Elle suppose les migrations/états de §4.3 ; Codex relit.

## 8. Décisions de l'utilisateur (2026-10-15)

- **Q1** : une clé API Anthropic a été ajoutée par l'utilisateur. Elle ne doit **jamais** être lue, affichée, partagée ni commitée. Elle vit uniquement en variable d'environnement (`ANTHROPIC_API_KEY`) ; côté worker, en secret du dépôt GitHub. Cela annule la décision du 10/10 « pas de critique automatique », **pour ce style seulement**.
- **Q2** : oui, démarrer sans musique de fond (voix + bruitages synthétisés), puis tester Eleven Music.
- **Q3** : budget calculé à la section 9.
- **Q4** : option B (pas de pause) : tout est enchaîné ; « régénérer un plan » viendra après coup en phase 6.
- **Q5** : une seule vitrine, un seul décor réussi.
- **Q6** : une branche `explainer/phase-N` par phase côté moteur, PR web séparées.

## 9. Budget de rentabilité (estimations)

Tarifs Anthropic (cache du 2026-10-06, à revérifier) : Opus 5.5 4 $/20 $ par million de tokens, Sonnet 5.5 2 $/10 $ (lecture de cache 0,20 $), Haiku 5.5 0,10 $/0,50 $. Pour rester prudent, 1 $ est compté comme 1 €.

**Revenu net par crédit** (après TVA 20 % et frais Stripe ≈ 2,2 % + 0,25 €) :

| Canal | Prix TTC | Crédits | Net / crédit |
|---|---|---|---|
| Pro (89 €) à quota plein | 89 € | 40 | ≈ 1,80 € |
| Starter (19 €) | 19 € | 10 | ≈ 1,50 € |
| Pack (39 €) | 39 € | 30 | ≈ 1,05 € (pire cas) |

**Coût variable aujourd'hui** : ≈ 0,40 € par vidéo standard (voix 0,25, images 0,11, script et vérifications 0,04). L'Explainer n'a pas d'images : voix + script ≈ 0,29 €, plus le LLM.

**Coût LLM par vidéo (8 plans)**, hors tokens de réflexion (non mesurés) :

| Configuration | Typique | Pire cas |
|---|---|---|
| Tout en Opus 5.5 (réalisateur, animateur, critique) | ≈ 1,5 € | ≈ 3,2 € |
| Réalisateur Opus 5.5 + animateur et critique Sonnet 5.5, prompt mis en cache | ≈ 0,96 € | ≈ 1,6 € |

Détail de la 2e ligne : réalisateur 0,16 € ; animateur ≈ 0,60 € (8 plans × ~4 k tokens de sortie, 1,5 passe en moyenne) ; critique ≈ 0,20 € (1 tour). La sortie domine le coût ; le cache du prompt système (doc du runtime + plans de référence) rend l'entrée presque gratuite.

**Conclusion.** Au tarif d'une vidéo standard (1 crédit ≈ 1,05–1,80 € net) une vidéo Explainer coûterait **≈ 1,25 € en usage typique** (0,29 + 0,96) : marge nulle ou négative sur le canal pack. Il faut donc :
1. **Facturer 2 crédits par vidéo Explainer.** Revenu net 2,10 € (pack) / 3,00 € (Starter) / 3,60 € (Pro) contre un coût typique 1,25 € : marge brute **≈ 40 % (pack, pire canal), 58 % (Starter), 65 % (Pro)**. Un abonné Pro à quota plein ferait 20 vidéos Explainer.
2. **Modèles** : Opus 5.5 uniquement pour le réalisateur (appel unique, court). Animateur et critique en Sonnet 5.5, effort `medium`, prompt système en cache. Haiku 5.5 non retenu : le code d'animation est la partie la plus exigeante.
3. **Plafond dur par vidéo : 1,20 € de LLM** (pire cas toléré : coût total ≈ 1,50 €, marge ≈ 29 % sur le pack, toujours positive). À l'approche du plafond le moteur arrête les itérations, garde la meilleure version ou retombe sur Pillow pour les plans restants, et l'écrit au rapport. Le plafond est une variable d'environnement (`EXPLAINER_LLM_BUDGET_USD`), les tentatives échouées comptent.
4. **Rien n'est acquis avant mesure** : les tokens de réflexion adaptative et le nombre réel d'itérations sont inconnus. La phase 3 mesure le coût réel sur le banc de 5 sujets ; si le typique dépasse 1,00 €, on baisse l'effort, on réduit la critique à une planche par vidéo, ou on passe le prix à 3 crédits.

Le prix en crédits est une décision produit à valider avant la phase 6 ; les phases 1 à 5 n'en dépendent pas.

## 10. Phase 2 — kit d'illustration et vidéo vitrine (état)

**Fait** (branche `explainer/phase-2`)
- `runtime/kit-world.js` : personnages (pose assise, téléphone, sourire, clignement, 4 coiffures), maison en coupe (palettes Dakar et Paris, fenêtre avec baobab ou tour Eiffel), ville de nuit, tour d'antenne, océan en coupe avec rayons de lumière, fond marin, câble sous-marin lumineux, poissons, baleine, bateaux, station côtière, data center (baies, LED).
- `runtime/kit-tech.js` : `scramble`, `stageHud` ; `runtime/core.js` : `cameraR` (caméra avec rotation, pour le raccord zoom-through).
- `reference/showcase-dakar-paris.timeline.js` : vidéo vitrine de 60 s, écrite à la main (maison de Dakar, zoom dans l'écran, cinq étapes dans le téléphone, antenne, câble sous-marin, data center, appartement à Paris, réponse, récapitulatif).
- Tests : aucune erreur JS sur 121 instants, déterminisme entre scènes, narration et SFX dans la durée.
- Rendu mesuré en local (Windows) : 60 s, 1 800 images, 165 s.

**Auto-évaluation sur la grille de la section 6 (mon estimation, à contredire par ton regard)**

| Critère | Note | Remarque |
|---|---|---|
| Hook | 4 | pièce chaleureuse, téléphone qui s'allume, « DAKAR » ; pas de texte nécessaire |
| Continuité | 4,5 | zoom-through maison → écran, un seul monde Dakar → océan → Paris ; trois fondus au noir courts |
| Synchronisation | non évaluable | narration calée à la main, pas de voix réelle ; mesure en phase 3 |
| Lisibilité | 4 | bulles du téléphone lisibles ; les étiquettes du bas (36 px) sont sous les 64 px demandés pour les mots-clés |
| Clarté pédagogique | 4,5 | cinq étapes + réassemblage à l'arrivée ; sans le son, l'idée se comprend |
| Rythme | 4 | à vérifier à l'œil sur la vidéo entière |
| Finition | 4 | style plat cohérent ; les personnages restent simples (une pose assise) |
| Son | non évalué | bruitages synthétisés non écoutés par moi (aucune sortie audio) ; volume : crête −3,6 dB |
| Justesse | 4,5 | aucun chiffre, seulement des mécanismes généraux |

Moyenne des critères évaluables ≈ 4,2 : **sous la barre de 4,5 demandée.** L'acceptation de la phase 2 attend donc ton avis visuel et les retouches qui en découlent.

## 11. Phase 3 — réalisateur, animateur, validation, repli (état)

**Fait** (branche `explainer/phase-3`)
- `runtime/scene.js` : graphe de scène déclaratif (30+ éléments, `h.to/set/appear/follow`, caméra, SFX) : l'animateur n'écrit jamais sur le canvas. API décrite dans `prompts/runtime-api.md`.
- `director.py` (Opus 5.5) → storyboard validé par `schema.py` + ancres vérifiées dans la narration ; `animator.py` (Sonnet 5.5, prompt système mis en cache, 4 plans de référence, plans animés en parallèle, 2 corrections max, on garde la meilleure version) ; `validate.py` : liste blanche AST (esprima) + essai Chromium (erreurs, budget par image, texte coupé/chevauchant/zones d'interface, déterminisme) ; `Function.prototype.constructor` neutralisé dans la page ; `fallback.py` : scène Pillow `motion_graphics` pour un plan qui échoue, écrite au rapport ; `pipeline.py` : `explainer.report.json` (modèles, tokens, coût estimé par étape, itérations, replis, versions de prompts, de runtime et de Chromium).
- 31 tests Explainer (dont un pipeline complet avec LLM simulé, repli Pillow compris).

**Premier essai réel — sujet « le trajet d'un message »** (sans voix : timings estimés) : 8 plans, 0 repli, 3 corrections d'animateur au total, coût LLM **0,56 $** (plafond 1,20 $), rendu 168 s pour 79 s de vidéo. Limites constatées à l'œil : plusieurs plans ont des compositions faibles (décors coupés, zones vides, un grand rectangle vert), et la narration générée contient une affirmation à vérifier (« trois secondes plus tard ») : le contrôle de vérité sur la narration relève de la phase 4 (critique).
**Correction avant fusion (même sujet, mêmes phrases, relancé)** : le premier essai montrait un rectangle vert sur plusieurs plans. Cause : l'animateur avait passé `dark: true` (booléen) à la maison, ce qui invalidait une couleur du canvas, qui gardait alors la précédente. Corrections : le runtime refuse les props inconnues, les types faux et les couleurs invalides (le plan échoue à la validation et l'animateur le corrige), contrôle de « cadre presque vide » (couverture), règles de composition et formule de placement d'un personnage dans une maison dans l'API, nouveau plan de référence `house-room`, narration sans durée inventée. Second essai : 8 plans, 0 repli, 3 corrections ciblées, **0,68 $**, rendu 194 s ; plus de rectangle vert, décors plein cadre, plus de textes superposés. Restent faibles à l'œil : le plan d'ouverture (deux maisons en diagonale, encore proche de l'« écran coupé en deux »), un grand disque noir sur le plan des ondes radio, du sol vide en bas de certains plans.

**Pas encore fait** : les 4 autres sujets du banc, la moyenne ≥ 4 de la grille, la mesure de synchronisation (voix réelle après le 17).
