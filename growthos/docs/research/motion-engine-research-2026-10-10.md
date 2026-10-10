# Faceloop : moteur Motion Graphics avancé, rapport de recherche (2026-10-10)

Statut : recherche uniquement. Aucun code de production écrit ni modifié. Les faits observés sont séparés des hypothèses (H).

## 1. Évaluation générale

Faceloop a déjà un moteur motion graphics déterministe, local, sans appel API, avec garde-fous de mise en page. Le dépôt de référence ne contient PAS de code d'animation (voir 2) : il ne peut donc pas servir de bibliothèque de techniques, seulement de catalogue de briefs et de signal sur ce que les créateurs demandent. Recommandation : **adapter** (étendre le moteur Pillow + Manim existant), **reporter** tout moteur navigateur (HTML/Remotion/Three.js), **rejeter** l'exécution de code généré par LLM.

## 2. Ce que contient réellement `yihui-dev/awesome-opus5-5-videos` (observé, cloné le 2026-10-10, dernier commit 2026-10-08)

- 514 fichiers `.md` (un prompt chacun, `prompts/`), `data/videos.json` (513 entrées), README, licence MIT. **Zéro fichier source d'animation, zéro MP4, zéro HTML.** Les médias sont hébergés sur skillry.dev (non analysés : non récupérés).
- Catégories : motion 317, explainer 67, interactive 70, 3d 59. Tags (du « remake » Skillry, pas de l'original) : canvas 351, svg 219, threejs 147, shader 104, gsap 100, css 68.
- 234 sur 513 prompts sont `prompt_partial` (texte du post seulement). Médiane 180 caractères, max 22 367.
- Seuls 89 prompts mentionnent Remotion, 1 mentionne Manim, 17 mentionnent MP4. Aucun exemple de finance personnelle pédagogique : le plus proche est un film produit pour une app de comptabilité.
- Licence : le MIT couvre le dépôt. Les prompts appartiennent à leurs auteurs (chaque entrée renvoie au post original). On extrait des principes, pas de contenu.
- Limite : les tags techniques décrivent le remake Skillry, pas forcément la technique de l'original (ex. le film Taxtello est annoncé « React + Remotion » dans son prompt, tagué « Canvas, SVG, CSS »).

Conclusion factuelle : ces vidéos sont du **code écrit par l'IA pour chaque vidéo** (HTML/Canvas/Remotion), pas un moteur réutilisable. C'est l'inverse du modèle Faceloop (LLM directeur + moteur déterministe).

## 3. Cinq prompts de référence (lecture des prompts uniquement, rendus non inspectés)

| # | Slug | Domaine | Techno déclarée | Faits observés | Réutilisable pour Faceloop |
|---|------|---------|-----------------|----------------|----------------------------|
| 1 | daniel-haida-636937 | Finance / comptabilité | React + Remotion (prompt) ; tag Canvas/SVG/CSS | Film produit 15 s, charte réelle (tokens CSS, polices, captures d'écran), règles « un plan = une idée », musique synthétisée en Python | Principes de direction (une idée par scène, peu de texte, charte stricte). Pas la techno (UI produit réelle absente chez nous) |
| 2 | linearuncle-971663 | Maths | Manim + edge-tts (prompt chinois d'une ligne) | Dérivée « expliquée avec exemples », voix TTS | Confirme Manim pour les maths ; on l'a déjà (`manim_backend.py`) |
| 3 | astrothewizard-618782 | Éducatif narratif | Canvas, JS pur, 60 s 1080p60 | Simulation réelle (marche aléatoire), chiffres réels, boucle de vérification (stills, mesure audio) | Idée de boucle de vérification par stills ; on a déjà `preflight.py` |
| 4 | alex-prompter-997524 | Explainer promo | SVG + GSAP, page HTML, 5 scènes | Gabarit de 5 scènes, 30 s | Structure en scènes typées : proche de nos `sceneType` |
| 5 | brainextends-606193 | Typographie cinétique / UI | Shader + SVG, MP4 1080p60 | Brief très spécifié (scène, palette, typo, 18 s) | Spécification déclarative riche : analogue à notre schéma, plus dense |

Données financières (barres, courbes) : aucun exemple propre dans le dépôt ; ces visuels existent déjà chez nous (`bar_chart`, `donut_chart`, `compound_growth`).

## 4. Architecture Faceloop actuelle (code lu)

Flux réel : script → blocs avec `motion_graphic` (JSON) → `visuals.fetch_motion_graphics_clips` → `motion_graphics.render_scene_clip` (un `.mp4` muet par bloc à durée exacte) → `video.py` assemble avec ffmpeg, voix ElevenLabs, sous-titres `.ass`.

- `engine/motion_graphics/schema.py` : 15 `sceneType` (big_number, money_split, progress_bar, bar_chart, donut_chart, comparison, before_after, timeline, compound_growth, checklist, warning, formula, equation_steps, function_graph, icon_text). Validation de structure, repli `icon_text`. **C'est déjà une spécification structurée : le LLM ne produit pas de code.**
- `renderer.py` : frames Pillow supersamplées x1,5, 25 fps, CRF 19, ffmpeg. Zéro API.
- `layout.py` / `preflight.py` : mesure du texte, anti-chevauchement, zone sûre, zone des sous-titres ; frame stable rendue à t=1 ; erreur → repli sûr.
- `sync.py` : révélations calées sur les mots ElevenLabs (`block-NN.words.json`).
- `manim_backend.py` (776 lignes) : Manim + LaTeX en sous-processus avec délai, modes `manim`/`auto`/`pillow` explicites, `.render.json` de diagnostic ; équations qui se transforment d'une étape à l'autre.
- `kinetic_typography.py` (113 lignes) : typographie sur fond uni, extraction déterministe, très limitée.
- Tests : `test_motion_graphics*.py`, `test_math_*`, `test_kinetic_typography.py`, `test_captions.py`.
- À PRÉSERVER : contrat « jamais bloquant », repli, zone sûre, déterminisme, absence d'appel réseau.

## 5. Limites actuelles (partiellement hypothèses : je n'ai pas inspecté de vidéos rendues dans cette recherche)

- Observé dans le code : chaque scène est un clip indépendant ; aucune transition entre scènes ; pas de caméra ; easing limité à quelques fonctions (`animations.py`, 104 lignes) ; un seul style de scène par bloc (pas de composition d'éléments multiples). Typographie cinétique réduite à 113 lignes.
- (H) La qualité perçue est limitée surtout par l'absence de transitions/caméra et la pauvreté de composition, pas par Pillow en soi. À valider sur les vidéos du kit `docs/benchmark/`.
- Vitesse de rendu Pillow et mémoire : **non mesurées ici**.

## 6. Comparaison des technologies

| Option | Qualité | Déterminisme | Serveur sans écran | Maths | Sécurité | Coût d'ajout | Avis |
|--------|---------|--------------|--------------------|-------|----------|--------------|------|
| Pillow (existant) | moyenne, plafonnée | total | oui | limité | excellente | nul | étendre |
| FFmpeg (existant) | transitions, zoom, mélange | total | oui | non | excellente | faible | **utiliser pour transitions** |
| Manim (existant) | élevée pour maths | élevé | oui (LaTeX requis) | excellente | bonne (sous-processus) | déjà payé | garder, limité aux maths |
| HTML/CSS + GSAP / Canvas / SVG | élevée | moyen (horloge à contrôler) | via navigateur sans écran | MathJax | **risque élevé** si contenu généré | runtime Chromium | reporter |
| Remotion | élevée | bon | Chromium + Node | via KaTeX | idem ; licence payante selon taille d'entreprise (à vérifier) | nouveau runtime | reporter |
| Three.js / WebGL | élevée en 3D | moyen (GPU) | logiciel lent | non | idem | élevé | rejeter pour l'instant |

Coût par minute rendue : **non mesuré**. Le coût mesuré le 25/09 (~0,34-0,37 $/vidéo) vient surtout d'images, TTS et LLM, pas du rendu Pillow local.

## 7. Architecture cible recommandée

Garder le pipeline actuel. Le « renderer selection » de l'hypothèse du brief existe déjà sous forme de `sceneType` → fonction (Pillow ou Manim). Ajouter, par ordre d'utilité supposée :
1. Transitions entre blocs au montage ffmpeg (`xfade`) : pas de nouveau runtime, déterministe.
2. Primitives de composition dans Pillow : plusieurs éléments par scène, easing étendu, léger mouvement de caméra (zoom/pan sur la frame supersamplée).
3. Étoffer la typographie cinétique (mots synchronisés, mise à l'échelle) dans `kinetic_typography.py`.
Un moteur navigateur n'est justifié que si le benchmark montre un écart que 1 à 3 ne comblent pas.

## 8. Sécurité

Ne jamais exécuter HTML/JS/SVG généré par un LLM dans l'application. Risques d'un moteur navigateur : exécution de code arbitraire, SSRF, accès fichiers, SVG non fiable, boucles infinies, épuisement des ressources, isolation multi-tenant. Si un jour nécessaire : composants allowlistés pilotés par JSON validé (jamais de code), worker isolé sans réseau, limites CPU/mémoire/temps, polices et médias locaux uniquement. L'architecture actuelle (JSON validé → fonctions Python de confiance) respecte déjà ce principe.

## 9. Coûts et performance

Aucun appel API ajouté par 1 à 3. Pas d'impact Vercel ni Supabase (rendu côté worker GitHub Actions, d'après la mémoire projet). Un moteur Chromium alourdirait le worker (installation, mémoire) : à chiffrer seulement si on y va. Aucun chiffre de durée inventé ici.

## 10. Benchmark proposé

Réutiliser `docs/benchmark/` (briefs.json + PROTOCOL.md, 30 briefs, 5 vidéos déjà rendues sur `@Benchmark`). Étendre avec les 5 cas du brief : PocketLogic, ArgentSimple, équation, explainer éducatif, récit en typographie cinétique, mêmes script/voix/charte avant et après. Critères : ceux du brief, notés par inspection de frames réelles (image par image sur transitions) + mesures objectives (durée de rendu, coût, échecs de preflight, collisions de sous-titres). Aucune note avant d'avoir les vidéos.

## 11. Feuille de route

- **A. Baseline** (aucun code) : rendre les 5 cas actuels, inspecter, mesurer durée/mémoire. Critère : tableau de référence signé par l'utilisateur. Rollback : sans objet.
- **B. Prototype** : transitions `xfade` entre blocs motion_graphics derrière un drapeau d'environnement. Fichiers : `engine/video.py` (assemblage), tests associés. Critère : sous-titres et synchro audio intacts, durée totale exacte, vidéo comparée à A. Rollback : drapeau désactivé.
- **C. Composition** : primitives multi-éléments + caméra légère dans `animations.py`/`scenes.py`, preflight inchangé. Critère : 0 régression des tests de mise en page, benchmark meilleur sur composition/fluidité.
- **D. Typographie cinétique** étoffée, calée sur `sync.py`.
- **E. Décision moteur navigateur** uniquement si A à D laissent un écart prouvé ; sinon abandon.
Chaque phase : tests existants + tests ciblés, pas de migration, pas de changement d'infrastructure.

## 12. Risques et compromis

Les transitions peuvent décaler la synchro voix/sous-titres (durées des clips) : à tester en premier. Le gain visuel réel est une hypothèse tant que A n'est pas fait. La licence Remotion et le poids de Chromium sont à vérifier avant tout engagement.

## 13. Décision

**Adapter** : étendre Pillow + ffmpeg + Manim. **Reporter** le moteur navigateur. **Rejeter** le code généré par LLM exécuté en production.

Faisable maintenant : transitions, composition multi-éléments, typographie cinétique. Effort modéré : caméra, nouveaux types de scènes. Trop cher/complexe : parité avec des animations « code unique par vidéo » (HTML/Canvas écrit par l'IA pour chaque vidéo), car cela casse déterminisme, coût et sécurité. Gain le plus probable en premier (hypothèse à valider par A) : transitions entre scènes. À éviter explicitement : exécuter du code généré, ou introduire Remotion/Three.js avant d'avoir mesuré l'écart.

Réponse à la question finale : une qualité *comparable en polish* est atteignable pour les formats structurés (finance, maths, listes) ; la qualité « film d'auteur » du dépôt de référence ne l'est pas, car elle repose sur du code sur mesure pour chaque vidéo.
