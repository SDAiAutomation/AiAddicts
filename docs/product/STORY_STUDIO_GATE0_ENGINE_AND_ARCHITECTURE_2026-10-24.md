# Story Studio — Gate 0 : audit du code, choix du moteur, architecture cible, feuille de route

Date : 2026-10-24. Auteur : Claude Code. Complète `STORY_STUDIO_GATE0_REFERENCE_ANALYSIS_2026-10-24.md`.
Légende : **[VÉRIFIÉ]** = lu dans le code ou interrogé en lecture seule aujourd'hui ; **[NON VÉRIFIÉ]** = supposition ou source tierce ; **[ESTIMATION]** = jugement, jamais une mesure.

## 1. Audit du code réel

### 1.1 Parcours effectif d'un projet Story [VÉRIFIÉ, lecture de `growthos/mvp` et `growthos-web@master`]
Éditeur (`story-editor.tsx`) → `saveStoryProject` (`content_items.script.story`, statut `idea`) → `queueStoryGeneration` (flag serveur `STORY_GENERATION_ENABLED`, admin plateforme, rôle, case « payant » cochée, ≤ 3 tentatives, validation miroir, modération, solde > 0) → statut `queued` + dispatch GitHub Actions → `worker.process_one` → `assembler.run_for_content_item` (réserve le crédit, rembourse en cas d'échec) → `script.normalize_script` → **`story_compile.compile_story`** → blocs historiques → TTS ElevenLabs par bloc (voix du personnage) → **une image OpenAI par bloc** (`visuals.fetch_block_images`, repli Pexels) → **Ken Burns `zoompan`** (`video.py`) → sous-titres → upload `content-videos` → `video_url`.

### 1.2 Réponses aux 10 questions

1. **Pourquoi des scènes illustrées et pas de l'animation ?** `compile_story` traduit chaque plan en *un seul bloc narré* : `{text, voice_id, speaker_id, visual: "<Nom> speaking, illustrated character shot"}`. Le contrat d'un plan (`validator.py`) ne contient que `id, speaker_id, dialogue, duration_s`. Il n'y a **ni action, ni émotion, ni geste, ni caméra, ni décor, ni accessoire** ; le moteur visuel ne sait produire qu'une image fixe par bloc + zoom lent. Le rendu est donc un diaporama animé, par construction.
2. **À conserver** : éditeur et sauvegarde de brouillons, verrous de mise en file, worker partagé et réclamation conditionnelle des jobs, RPC de crédit atomiques (`reserve/refund_generation_credit`), voix par bloc et catalogue de voix, `story_intelligence` (validateur, `timing.align_storyboard`, `voice_catalog`, tests), FFmpeg/assemblage final, stockage et versionnement. Miroir Python/TS du validateur avec fixture commune.
3. **À remplacer** : uniquement l'étape « visuels » pour les projets animés (nouveau renderer derrière une interface). Le rendu `story_animation_spike` (PR #72) ne sera pas réutilisé comme renderer ; ses tests de contrat de timeline peuvent inspirer les nouveaux.
4. **Contrat manquant** : `ShotPlan v1` (§3.2) — acteurs présents, action (verbe d'un catalogue fermé), émotion, regard, accessoires, décor, cadrage, mouvement de caméra, transition, intention de plan, sorties de budget.
5. **Nouveau renderer sans casser l'existant** : `story.version` 1 reste compilé par `story_compile` ; `story.version: 2` + `animation_schema_version: 1` active un chemin distinct, sous flag **OFF par défaut** (variable serveur et option par organisation). Aucune migration SQL requise : tout reste dans `script` jsonb.
6. **Audio → animation** : l'audio est généré **d'abord**. `timing.align_storyboard` existe mais accepte des durées « fournies par l'appelant, non vérifiées » : il faut les **mesurer par `ffprobe` sur les MP3 réels**, puis fixer la durée de chaque plan = audio mesuré + respiration. Les visèmes (piste rigged) viennent de l'audio décodé ; la piste générative exige une approche de lip-sync dédiée (§2).
7. **Cohérence des personnages** : une « fiche de personnage » versionnée (`character_sheet`) = images de référence validées + palette + proportions + voix, résolue **côté serveur** par identifiant (jamais de chemin fourni par l'IA). Contrôle qualité automatique de similarité entre plans (à mesurer en Gate 1).
8. **Coût réel par vidéo** : un `render_report` écrit dans `script` à chaque rendu (appels fournisseurs, secondes générées, caractères TTS, temps CPU, tentatives) + budget dur par vidéo dans le contrat. Aujourd'hui rien de tel n'existe pour Story et `STORY_STUDIO_FIRST_RENDER.md` confirme que **l'E2E n'a jamais tourné**.
9. **Sécurité** : voir §4.
10. **Évolutivité** : renderer = interface `StoryAnimationRenderer` + registre (`illustrated_v1`, `rig_v1`, `genvideo_v1`, …) ; contrat versionné ; catalogues fermés d'actions/caméras/décors extensibles sans changer le worker.

### 1.3 Sécurité et état réel [VÉRIFIÉ aujourd'hui, lecture seule]
- Requête `select … from storage.buckets` sur le projet Supabase `growthos` (`lclesqfokgetznhepgmj`, ACTIVE_HEALTHY) : **`content-videos` : `public = false`**, limite 200 Mio, MIME autorisés `image/jpeg, text/plain, video/mp4`. `content-assets`, `autoedit-sources`, `autoedit-results` : privés. **Le doute « bucket public » est levé.** Le second projet « SDAiAutomation's Project » est INACTIVE.
- Subsiste : `storage._upload` utilise `upsert="true"` ; l'immutabilité des chemins `<id>/v<n>.mp4` repose sur la convention, **non prouvée** par test. Les `video_url` stockés sont des `get_public_url(...)` historiques : la lecture exige une URL signée côté web (à tester, hors périmètre Gate 0).
- Preview et Production partagent le même projet Supabase (cf. `STORY_STUDIO_FIRST_RENDER.md`) : **aucun test d'écriture ne sera fait sur ce projet** sans accord.
- CI [VÉRIFIÉ] : PR #72 `offline-contract-and-render` = **échec** (`ffmpeg` absent du runner). PR #71 : seuls des contrôles « skipping ». Derniers runs `GrowthOS worker`/`health` sur `growthos/mvp` : succès. Les tests `story_intelligence` n'ont **pas** été exécutés ici (pas de pytest sur ce poste, rien d'installé).
- Autres branches pertinentes déjà dans le dépôt : `feat/animated-story-engine-prototype` (planification déterministe + budget + exécuteur à fournisseurs injectables : 435 lignes, **à auditer en Gate 4** car l'idée « budget gate » est bonne), `feat/wow-offline-animation-poc` (autre POC Pillow, même verdict), `docs/faceloop-wow-hybrid-animation-strategy-2026` (PRD). Rien n'est à fusionner maintenant.

## 2. Comparatif des approches

Ce poste de travail : Intel i3-1005G1, 8 Go de RAM, **aucun GPU dédié**, Godot/Blender **non installés** → **aucun benchmark moteur n'a été exécuté en Gate 0**. Les notes sont des [ESTIMATIONS] argumentées, à confirmer en Gate 1. Échelle : ★ faible … ★★★★★ fort.

| Critère | A. Godot 2D squelettique | B. Blender Grease Pencil | C. Live2D | D. Rive | E. Génération vidéo IA (image→vidéo) | F. Hybride : rig pour personnages récurrents + génératif pour inserts |
| --- | --- | --- | --- | --- | --- | --- |
| Fidélité aux références | ★★ (limitée par l'art rigué) | ★★★ (dessin 2D à la main possible, lent) | ★★ (face/buste, pas le corps entier) | ★★ | **★★★★** (c'est la voie la plus plausible des références, **[HYP]**) | ★★★★ |
| Animation / acting | ★★★ (contrôle total, travail de rig) | ★★★★ (acting réel, travail manuel énorme) | ★★ (très bon visage/buste) | ★★★ (machines d'états) | ★★★★ mouvement riche, ★★ contrôle | ★★★★ |
| Cohérence des personnages | ★★★★★ (assets fixes) | ★★★★★ | ★★★★★ | ★★★★★ | ★★ à ★★★ (références d'images, dérives vues dans les références) | ★★★★ |
| Lip-sync | ★★★★ (visèmes pilotés par l'audio) | ★★★ | ★★★★ | ★★★ | ★ à ★★ (à tester ; **[NON VÉRIFIÉ]** par modèle) | ★★★★ sur les plans de dialogue |
| Pilotage par script/API | ★★★★ (`--headless`, `--write-movie` documentés) | ★★★ (Python headless, lourd) | ★★ | ★★★ | ★★★★★ (API) | ★★★★ |
| Coût marginal par vidéo | ★★★★★ (CPU) | ★★★★ | ★★★★ | ★★★★ | **★★ à ★★★** : voir ci-dessous | ★★★ |
| Coût de création des assets | **★★ (le vrai coût : illustration + rig + décors)** | ★ (très élevé) | ★★ | ★★ | ★★★★ (images-clés) | ★★★ |
| Performance (poste i3, runner CI) | ★★ (rendu logiciel, lent mais faisable ; **non mesuré**) | ★ | ★★ | ★★★ | ★★★★★ (hors machine) | ★★★ |
| Déploiement dans l'infra actuelle | ★★★ (binaire à installer sur le runner Actions ; **à mesurer**) | ★★ | ★ | ★★ | ★★★★★ (appel HTTP + ffmpeg) | ★★★ |
| Maintenance | ★★★ | ★★ | ★★ | ★★★ | ★★★ (dépendance fournisseur, modèles qui changent) | ★★ |
| Droits | Godot : licence permissive **[NON VÉRIFIÉ ici]** | Blender : GPL, sortie non concernée **[NON VÉRIFIÉ ici]** | **contrat de licence de diffusion payant au-delà d'un seuil de chiffre d'affaires, exclusions** (recherche web, sources divergentes sur le seuil) | runtime MIT annoncé pour Android ; **conditions du rendu serveur non trouvées** | **conditions d'usage commercial, droits sur les sorties, filigrane : à lire fournisseur par fournisseur** | cumul |

**Coût de génération vidéo — ordres de grandeur sourcés, non mesurés :** une comparaison d'octobre 2026 cite de ≈ 0,025 $/s (Wan 2.6 flash, 720p, muet) à ≈ 1,50 $/s selon les fournisseurs ; des revendeurs affichent ≈ 0,045–0,134 $/s pour Seedance et ≈ 0,08–0,11 $/s pour Kling/Veo, **avec des chiffres contradictoires** ([developersdigest.tech](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026), [atlascloud.ai](https://www.atlascloud.ai/blog/case-studies/Top-5-ai-video-apis-compared-speed-latency-and-cost-per-second-2026)). Pour un plan de 4 s et un taux de rebut inconnu (×1 à ×4 [ESTIMATION]), 15 plans pour une vidéo de 60 s donnent **un ordre de grandeur de quelques dollars à quelques dizaines de dollars par vidéo** : à confronter au prix réel d'un crédit Faceloop avant toute décision. **Cette fourchette n'est pas une mesure.**

### Lecture
- Les références mélangent deux besoins : (1) **2-3 personnages récurrents** à identité stricte en dialogue ; (2) **dizaines de plans-métaphores** à cohérence de *style* seulement. Ce sont deux problèmes distincts.
- **Rig 2D pur** : contrôle, coût marginal minimal, lip-sync fiable, mais **plafond artistique fixé par le travail d'illustration et de rigging**. Atteindre « corps entier avec accessoires » à ce niveau est un projet d'animateur, pas de script. Probabilité d'égaler le niveau des références sans artiste : **faible [ESTIMATION]**.
- **Vidéo générative pure** : meilleure plausibilité de niveau visuel, pire pour le contrôle, le lip-sync, la cohérence stricte et le coût prévisible ; dépendance et droits à auditer.
- **Hybride (F)** : colle à la structure des références (dialogue récurrent vs inserts), au prix de deux chaînes à maintenir. **Mon a priori**, sans preuve.
- Live2D et Rive : bons pour le buste/visage, **hors cible** pour du jeu de corps complet ; Live2D est écarté d'emblée (licence). Blender GP : écarté pour l'automatisation (coût de création d'assets).

## 3. Architecture cible (modulaire, pas de microservices)

```
Idée/script (UI existante)
  → NarrativePlan  (dialogue + intention émotionnelle)       [existant étendu : champs optionnels]
  → ShotPlan v1    (action, émotion, caméra, décor, assets)  [NOUVEAU, validé Python + TS, fixtures croisées]
  → Audio d'abord  (TTS existant → ffprobe des durées réelles → retiming `timing.py`)
  → Renderer       (interface unique, registre : rig_v1 | genvideo_v1 | illustrated_v1)
  → QC automatique (durées, noir/gel, crêtes audio, cohérence personnage, zone sous-titres)
  → Assemblage FFmpeg (sous-titres, musique, SFX, loudness) → stockage privé existant
```
Un seul dépôt, un seul worker, **un package `growthos/engine/story_animation/`** (contrat, résolution d'assets, interface renderer, QC, rapport de coût). Pas de service externe supplémentaire.

### 3.1 Interface renderer
```python
class StoryAnimationRenderer(Protocol):
    name: str; version: str
    def estimate(self, plan: ShotPlan) -> CostEstimate: ...      # sans effet de bord, appelée avant réservation de crédit
    def render_shot(self, shot: Shot, ctx: RenderContext) -> ShotClip: ...  # clip muet + métriques
```
L'assemblage audio, les sous-titres et l'upload restent communs.

### 3.2 `ShotPlan v1` (esquisse à valider avant code)
Par plan : `id`, `setting_id`, `shot_type` (`wide|medium|close_up|insert|over_shoulder`), `camera` (`static|push_in|pull_out|pan_l|pan_r`), `actors[{character_id, pose|action, emotion, gaze, props[]}]`, `speaker_id`, `dialogue`, `intent` (une phrase), `transition_in`, `beats[{t, event}]` pour les moments d'action synchronisés à l'audio. **Verbes d'action et catalogues de décors/props = listes fermées côté serveur** ; l'IA propose, le serveur valide ; aucun chemin ni URL venant de l'IA. Plafonds : acteurs/plan, plans/vidéo, durée, secondes générées.

### 3.3 Coûts, cache, budget
`budget{max_provider_calls, max_generated_seconds, max_usd}` dans le contrat ; refus **avant** la réservation du crédit si l'estimation dépasse ; **cache** par hash `(renderer_version, shot normalisé, refs, seed)` ; **prévisualisation** par storyboard fixe (gratuit) puis rendu final ; `render_report` consigné dans `script` ; aucune table nouvelle tant que non justifiée.

### 3.4 Qualité automatique (réutilise l'idée de `feature/render-av-checks-20261011`)
Durée vs audio mesuré, écran noir/gelé, crête audio, loudness cible (les références sont à ≈ −12 LUFS, **à ne pas copier aveuglément**), sous-titres dans la zone sûre, similarité du personnage entre plans, détection de plans quasi identiques. **La revue humaine reste obligatoire à chaque gate.**

## 4. Exigences de sécurité du nouveau chemin
Isolation par `account_id`/organisation (préfixe de stockage par locataire, jamais de chemin fourni par le client) ; fiches et assets résolus côté serveur ; téléchargement de sorties fournisseurs avec liste blanche d'hôtes, taille/durée maximales, type MIME vérifié (anti-SSRF, anti-fichier malveillant) ; clés dans les secrets Actions uniquement ; journaux sans prompts utilisateur complets ni URL signées ; plafonds de concurrence et de crédits ; remboursement sur tout échec après réservation, **y compris crash worker** (récupération des jobs abandonnés à tester) ; tests de régression Standard/Quiz avant tout branchement ; flag OFF par défaut ; pas d'essai sur le projet Supabase de production.

## 5. Risques et coûts

| Risque | Gravité | Atténuation |
| --- | --- | --- |
| Niveau artistique insuffisant avec la voie rigged | haute | bake-off Gate 1 avec le même brief, jugement visuel de l'utilisateur |
| Coût de génération supérieur au prix du crédit | haute | mesure sur échantillon plafonné, budget dur, cache |
| Incohérence/dérive des personnages en génératif | haute | fiches de référence, plans courts, QC de similarité |
| Droits de sortie et ToS fournisseur | haute | lecture des conditions **avant** tout choix, fournisseur remplaçable derrière l'interface |
| Lip-sync générative insuffisant | moyenne | dialogues en plans moyens/larges ou pistes rigged pour les gros plans parlants |
| Performance CPU du rendu rigged | moyenne | mesure ; rendu sur runner Actions ; basse résolution pour prévisualisation |
| Dépendance à un modèle qui change | moyenne | interface + version épinglée + cache des clips |
| Régression Standard/Quiz | haute | chemin séparé, flag OFF, tests |

**Coûts engagés à ce jour : 0 $** (aucun appel payant, aucune installation, aucune écriture distante). Les seules actions distantes : lecture GitHub et un `SELECT` sur `storage.buckets`.

## 6. Feuille de route

| Étape | Livrable | Preuve |
| --- | --- | --- |
| **Gate 1 — bake-off** (même brief, 5–8 s, 2 pistes) | Piste R : personnage original illustré + rig + décor + caméra (Godot ou équivalent) ; Piste G : mêmes personnages par fiche de référence + image→vidéo | 2 MP4 + coût mesuré + temps de rendu + notes ; **jugement visuel de l'utilisateur** |
| Gate 2 | 2 personnages, voix distinctes, durées audio mesurées, visèmes ou lip-sync mesurable | MP4 avec audio, mesures |
| Gate 3 | 15–30 s, 9:16, ≥ 3 plans, 2 récurrents | MP4 validé visuellement |
| Gate 4 | Contrat versionné, flag OFF, worker, crédits/remboursements, quotas, stockage privé, E2E, monitoring, rollback | tests verts exécutés, E2E sur environnement isolé |
| Prérequis transversal | Test d'immutabilité des versions, lecture signée du bucket privé, CI verte | rapports d'exécution |

Aucune de ces étapes n'est lancée sans l'approbation de l'utilisateur (voir bilan Gate 0).
