# Contrat des étapes et rendu des vidéos de résolution d'équations

Périmètre mathématique : voir [MATH_CHANNEL_FORMAT.md](MATH_CHANNEL_FORMAT.md). Ce document décrit
**comment une scène `equation_steps` devient une vidéo** : le contrat d'une étape, le plan calculé, la
synchronisation sur la voix réelle, les modes de rendu et les commandes pour reproduire.

## Chemin réel de génération

```
script.json ──► script.validate_script ──► voix ElevenLabs (+ mots horodatés) ──► plan d'étapes
 (équations)     math_validation : refus     assembler._synthesize_block           math_steps.build_plan
                 AVANT tout crédit           audio/block-NN.words.json             (visuals._sync_and_preflight)
                                                                                       │
        MP4 final ◄── ffmpeg (assemblage + sous-titres) ◄── clip Manim ◄── manim_backend (sous-processus)
```

- **Un seul plan** (`scene["_plan"]`) porte les étapes, les opérations et les instants ; le rendu le
  joue sans rien recalculer. Le calcul mathématique reste dans `math_validation.py`.
- **Temps de lecture** : si la voix s'arrête avant que le dernier résultat ait eu son temps de lecture
  (`result_hold`), du **silence est ajouté à l'audio du bloc** (`assembler._synthesize_block`) : la durée
  du bloc, les sous-titres et la timeline restent cohérents. Rien n'est compressé.

## Contrat d'une étape (script)

| Champ | Rôle |
|---|---|
| `equation` | texte mathématique, **seul champ obligatoire** (validé exactement) |
| `explanation` | annotation courte AFFICHÉE près de l'opération (`−6 des deux côtés`) |
| `spoken` | repère vocal : l'opération est nommée à cet instant (`on retire six`) |
| `sidesSpoken` | repère vocal de « aux deux membres » (sinon cherché après `spoken`) |
| `resultSpoken` | repère vocal du résultat (sinon : le mot qui suit le « : » prononcé, sinon le mot suivant) |

Au niveau de la scène : `verify: true` ajoute la vérification par substitution dans l'équation
d'origine (uniquement pour une solution unique du premier degré), `verifySpoken` la cale sur la voix,
`rhythm` surcharge les durées. **Les anciens scripts restent valides** (aucun champ nouveau requis ;
sans repères vocaux le rythme est régulier et signalé `timing: "fallback"`).

Les repères comparent des mots **normalisés** (mots-outils retirés : « on », « des », « un »… ne
comptent pas). Un repère composé uniquement de mots-outils est ignoré : choisir un mot plein
(`on retire`, pas `on retire un`). Utiliser un « : » dans la narration avant le résultat aide à le caler.

## Plan calculé (`math_steps.build_plan`)

Par étape : `id`, `equation`, `left`/`right` (LaTeX d'affichage), `operation` (`kind` = `add` / `mul` /
`div` / `rewrite` / `unknown`, `tex`, `display`), `intermediate` (l'équation avec l'opération écrite des
deux côtés), `cancel` (rang du terme annulé par côté), `narration`, `annotation`, `validation`
(`verified` / `invalid` / `unverified` + raison + valeurs exclues), `events`
(`showOp` → `sides` → `apply`, en secondes dans le bloc). Au niveau du plan : `timing`
(`voice` / `fallback`), `verification`, `neededDuration`, `warnings`.

Trois représentations séparées : **structure mathématique** (`operation`, termes), **LaTeX d'affichage**
(`left`, `right`, `tex`), **texte de la voix** (le `text` du bloc, jamais écrit par ce module).

Avertissements : `rhythm_tight:stepK:…` (la voix va plus vite que les durées minimales : l'animation
n'est PAS compressée sous son plancher, l'événement est retardé et le bloc passe en revue
`rhythm_review`), `voice_anchor_missing:stepK` (repère introuvable → rythme de repli),
`duration_short:…` (comblé par du silence en fin de bloc). Si la voix est trop rapide, **ralentir la
narration ou scinder en deux blocs** plutôt que d'exiger une animation illisible.

Durées (valeurs à tester, pas des normes) : `math_steps.RHYTHM`, surchargeables par la scène
(`rhythm`) ou `MATH_RHYTHM_JSON='{"result_hold": 2}'`.

## Mise en scène (Manim)

Équation centrale, **signe « = » immobile**, une seule échelle pour toute la scène. Séquence d'une
étape : l'opération apparaît (`−6`) avec son annotation → elle est écrite **des deux côtés** de
l'équation → les termes opposés s'annulent → le résultat remplace la ligne. Les lignes déjà résolues
montent en historique. Aucune transformation de formes entre équations différentes (fondu enchaîné) :
seules les parties identiques (`3x` → `3x`) se déplacent, par rang de terme, jamais par correspondance
automatique de LaTeX. Couleurs : texte neutre, accent pour l'opération et le changement, vert pour le
résultat (rouge pour « aucune solution »). Le contenu reste dans la zone 12 %–58 % de la hauteur, au-dessus
des sous-titres.

## Modes de rendu (`MATH_RENDERER`)

| Mode | Comportement |
|---|---|
| `manim` | **qualité finale** : Manim + LaTeX + dvisvgm + ffmpeg exigés. Dépendance manquante ou échec → `MathRenderError` (message exploitable, le job peut être repris) ; **jamais** de repli silencieux. Contrôle préalable avant tout rendu. |
| `auto` (défaut) | Manim si installé (et LaTeX pour une équation), sinon repli Pillow **avec la raison au rapport**. |
| `pillow` | aperçu / rendu simplifié, jamais Manim. |

En mode `manim`, deux garde-fous évitent de livrer une vidéo dégradée :
- le contrôle de mise en page du préflight Pillow (qui mesure la géométrie du rendu Pillow, pas celle de Manim) ne remplace plus la scène par un simple texte : il est consigné (`pillowPreflightIgnored`) et c'est le contrôle de Manim qui décide ;
- une alerte de mise en page bloquante du rapport Manim (`out_of_frame_x`, `out_of_content_zone_y`, `history_overlap`, `history_overlaps_equation`) lève `MathRenderError` avant l'écriture du clip. En `auto`, elle reste au rapport.

Titres : en majuscules, sauf les variables et les expressions (`Isoler x` → `ISOLER x`, `x ≠ 1` inchangé), via `display_text.display_title`.

Équation très asymétrique (échelle sous 1,2 : par exemple `(x − 2)(x − 3) = 0`) : le signe « = », toujours fixe d'une étape à l'autre, est décalé pour équilibrer l'équation et l'agrandir ; signalé dans `layout.info` (`balanced_equation`).

Chaque clip écrit `<clip>.render.json` : moteur demandé et utilisé, versions (Manim, LaTeX, ffmpeg),
raison du repli, mesures de mise en page (échelle, hauteur d'équation en px, `out_of_frame_x`,
`out_of_content_zone_y`, `history_overlap`, `history_overlaps_equation`), avertissements du plan, durée de rendu.

Contrôle de continuité d'un clip (la ligne d'équation ne se vide jamais le temps d'une transition) :
`python scripts/check_clip_continuity.py <clip.mp4>` (seuil calibré, voir l'en-tête du script ; il ne juge ni la lisibilité ni la synchronisation).

## Reproduire

```powershell
cd AiAddicts\growthos
$env:PYTHONPATH = "."
# vérification des dépendances du mode qualité finale
.\venv\Scripts\python.exe -c "from engine.motion_graphics import manim_backend as m; print(m.dependency_report())"
# vidéo de référence (3x + 6 = 18) et corpus : ElevenLabs uniquement, aucune écriture Supabase
.\venv\Scripts\python.exe scripts\generate_math_corpus.py content\scripts\maths-quality\ref-3x6.json --out output\math-quality\run
.\venv\Scripts\python.exe scripts\generate_math_corpus.py content\scripts\maths-quality\c1-negatif.json content\scripts\maths-quality\c2-distribution.json content\scripts\maths-quality\c3-fraction.json content\scripts\maths-quality\c4-quadratique.json content\scripts\maths-quality\c5-restriction.json --out output\math-quality\run
# cas qui doivent être REFUSÉS avant toute synthèse vocale
.\venv\Scripts\python.exe scripts\generate_math_corpus.py content\scripts\maths-quality\r1-racine-perdue.json content\scripts\maths-quality\r2-rationnelle-carre.json --out output\math-quality\run
# tests
.\venv\Scripts\python.exe -m unittest tests.test_math_steps tests.test_manim_backend tests.test_math_motion_graphics tests.test_clip_continuity
```

Aperçu d'une scène sans encoder de vidéo (rendu simplifié Pillow, à ne pas prendre pour le rendu final) :
`python -m engine.motion_graphics.preview <script> --block 2 --at 0,3,7 --duration 10 --words <block-02.words.json> --out out.png`.

## Limites connues

- Le plan n'écrit pas la narration : si la voix cite les étapes dans un autre ordre que les `spoken`, le
  plan retombe sur le rythme régulier (signalé). La justesse de l'explication orale reste une revue humaine.
- Les équations rationnelles, quadratiques et les pas « plusieurs opérations » n'ont pas d'équation
  intermédiaire animée (`operation.kind` = `unknown`/`rewrite`) : fondu enchaîné + annotation.
- Une scène sans LaTeX n'est jamais rendue par Manim en mode `auto` (qualité inférieure = rendu Pillow
  déclaré) ; le mode `manim` échoue explicitement.
- Durée d'un rendu Manim sous Windows avec MiKTeX (la composition LaTeX domine) : 60 à 80 s pour trois étapes, environ 240 s pour quatre étapes avec vérification. `MANIM_TIMEOUT_SECONDS` vaut 900 s par défaut. Le temps sur le worker GitHub n'est pas mesuré.
- Les lignes de l'historique avec fractions sont plafonnées à 0,8 unité de haut (0,62 à quatre étapes) pour tenir dans la zone : lisibles sur une image extraite, mais à contrôler sur un téléphone.
- Pendant un changement d'état, l'ancien et le nouvel état sont visibles ensemble à faible opacité (~0,2 s) : c'est le compromis retenu entre un trou et une superposition lisible.
