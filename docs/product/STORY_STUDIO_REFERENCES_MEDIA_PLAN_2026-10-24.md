# Story Studio — références et plan de réalisation (24 octobre 2026)

## Statut
Référentiel de décisions et inventaire des médias fournis par l'utilisateur. Documentation uniquement ; **aucun développement ni déploiement autorisé**. Les médias originaux sont des pièces jointes de la conversation, **pas** des fichiers binaires stockés dans GitHub par ce commit.

## Références vidéo reçues
- Vidéo A — titre à l'écran « Te voilà casé » ; fichier original `v26044gc0000dbbmjbvog65g5v9505sg.mp4`, copie réenvoyée `v26044gc0000dbbmjbvog65g5v9505sg(1).mp4`. Environ 2 min 01 s ; 512×910 ; ~30 fps. 
- Vidéo B — titre à l'écran « C'est garanti » ; fichier original `v26044gc0000dbdmes7og65jsu4osc70.mp4`, copie réenvoyée `v26044gc0000dbdmes7og65jsu4osc70(1).mp4`. Environ 1 min 39 s ; 512×910 ; 30 fps.
- Planche contact d'analyse : `story_video_contact_sheet.jpg` (fichier conversation/local, non poussé dans GitHub).
- Images montrées dans les réponses de ChatGPT : **illustrations de style recherchées, pas assets originaux ni images extraites des vidéos** ; leurs sources ne sont pas archivées. Ne pas les traiter comme des assets de production.
- Attention aux droits d'auteur : références pour analyse et inspiration ; ne pas republier, redistribuer ni copier les personnages/plans sans droits.

## Ce qu'on retient des références
- Direction artistique cible : cartoon rétro inspiré de l'animation « rubber hose » des années 1930, mais personnages et identité graphique **originaux**.
- Narration vivante, animaux anthropomorphes, gestes expressifs, expressions faciales, dialogues, cadrages et décors cohérents, sous-titres lisibles, transitions au service du récit.
- Ne pas confondre mouvements dans une vidéo et animation corporelle réelle : le MVP doit démontrer dans les pixels du MP4 des mouvements de rigs/personnages et interactions, pas seulement pan/zoom d'images fixes.
- Les vidéos de référence durent environ 1 min 39 s et 2 min 01 s ; commencer par un prototype de 15–30 s, puis viser 20–45 s et allonger après validation.

## Vision produit
Faceloop Story Studio est un **studio de dessins animés automatisé**, pas un générateur de diaporamas. L'utilisateur donne une idée ; l'IA prépare une seule fois un scénario structuré, les dialogues, les personnages, les émotions, les actions, les plans et les temps ; un moteur 2D déterministe utilise des rigs, animations, poses, décors et mouvements de caméra réutilisables. Synthèse vocale mise en cache, synchronisation, assemblage FFmpeg et export MP4 vertical 9:16. L'utilisateur peut modifier et régénérer un plan sans refaire toute la vidéo. Ne pas recourir par défaut à un modèle vidéo IA coûteux pour chaque scène.

## Architecture candidate (non validée)
Next.js / React / TypeScript (interface existante) → Story Intelligence Python GrowthOS (NarrativePlan, CharacterBible, ShotPlan JSON versionnés et validés) → bibliothèque d'assets et de rigs → moteur 2D automatisable → voix ElevenLabs avec cache → FFmpeg (montage/QC) → Supabase Postgres/Storage et Vercel. Isoler Standard et Quiz ; pas de Redis, Kubernetes ni GPU dédié sans justification.

## Moteur 2D : benchmark obligatoire
Comparer **Godot** (favori provisoire, non sélectionné), **Blender** et **Rive** sur :
1. animation de rigs et interactions multi-personnages ;
2. pilotage automatique depuis un JSON ;
3. synchronisation labiale, émotions, gestes et caméra ;
4. export vidéo automatisé/headless et reproductibilité ;
5. intégration aux workers Python, sécurité et performance ;
6. qualité artistique, coût, licence et maintenance.
Décision seulement après preuve sur une même scène test, pas par préférence théorique.

## Casting pilote et bibliothèque minimale
- **Néo** : jeune renard curieux, expressif, impulsif.
- **Orion** : vieux hibou calme, sage, observateur.
- Chaque personnage : cinq expressions (neutre, joie, surprise, colère, tristesse), six formes de bouche, cinq actions (marche, arrêt, regard, geste de conversation, réaction), trois orientations (face, trois-quarts, profil), voix stable, rig et assets versionnés.
- Ce casting est une fixture de validation, non une restriction du produit. Créer les designs originaux avant production.

## Prototype d'acceptation « Influence mentale »
15–30 secondes, 9:16, au moins trois plans, deux voix.
1. Néo entre et questionne Orion ; lèvres et gestes visibles ; Orion écoute/réagit.
2. Orion se penche, fait un geste, répond ; Néo change d'expression ; cadrage différent.
3. Néo recule et répond avec émotion ; caméra change ; apparence et décor cohérents.
Livrable obligatoire : **vrai MP4 visionné**. Refus si diaporama, mouvements de caméra seuls, incohérence des personnages, dialogue attribué au mauvais personnage ou absence de gestes. Mesurer durée de rendu, coût marginal, qualité du lip-sync et reproductibilité.

## Feuille de route indicative (non contractuelle)
1. Audit technique exhaustif des deux dépôts (3–5 jours estimés) : workers, stockage, jobs, fournisseurs, sécurité, tests et contrats.
2. Benchmark moteur 2D (4–7 jours) : Godot/Blender/Rive, mêmes cas d'usage et critères.
3. Prototype Néo–Orion (1–2 semaines) : rigs et MP4 réellement animé.
4. Story Intelligence v2 (1–2 semaines) : contrats JSON versionnés, validation, continuité.
5. Pipeline complet (2–3 semaines) : orchestration, cache, audio, FFmpeg, QC, coûts, retries, stockage.
6. Interface Studio (1–2 semaines) : casting, storyboard, preview, modification et régénération ciblée.
7. Stabilisation (1–2 semaines) : tests, sécurité, régressions, coût et lancement pilote.
**Estimation globale indicative : 9–15 semaines séquentielles**, à revoir après audit/spike.

## GO / NO-GO
- MP4 9:16 de 20–30 secondes réellement animé ;
- Néo et Orion cohérents dans trois plans ;
- personnages qui parlent et réagissent ; gestes et mouvements corporels visibles ;
- synchronisation bouche/voix acceptable et vérifiée ;
- rendu automatisé reproductible, coût et temps mesurés ;
- isolation multi-tenant, quotas, idempotence, tests de non-régression Standard/Quiz ;
- aucune nouvelle API payante, modification du code, PR, fusion ou mise en production sans accord explicite.

## Prochaines actions
Terminer l'audit **en lecture seule** ; benchmark et spécifications ; soumettre architecture et critères au propriétaire avant implémentation. Références de cadrage :
- `docs/product/STORY_STUDIO_DECISIONS_REPRISE_2026-10-24.md`
- `docs/product/STORY_STUDIO_CADRAGE_AUDIT_2026-10-24.md`
- `docs/product/STORY_STUDIO_ANIMATION_RECOVERY.md`
