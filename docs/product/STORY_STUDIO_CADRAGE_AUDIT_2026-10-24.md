# Faceloop Story Studio — dossier de cadrage et audit initial
Date : 2026-10-24
Statut : cadrage proposé ; NO-GO développement / production
Dépôts : SDAiAutomation/AiAddicts (growthos/mvp), SDAiAutomation/growthos-web

## Vision et décision produit
Story Studio doit transformer une idée en histoire **réellement animée** : personnages reconnaissables, mouvements corporels et faciaux, interactions, dialogues et voix, mise en scène, montage et export MP4 vertical 9:16. Un diaporama d'images avec voix off, même animé par pan/zoom, ne répond pas au besoin. L'utilisateur est réalisateur ; Story Intelligence assiste le scénario et la continuité. Story Studio reste un format de Faceloop à côté de Standard et Quiz.

## MVP et critères d'acceptation
1. Idée -> scénario éditable -> personnages -> plans décrivant actions et caméra -> clips animés -> voix -> MP4.
2. Références d'identité stables pour chaque personnage, voix assignée et vérifiée.
3. Au moins deux personnages interagissent physiquement et émotionnellement à l'écran.
4. Actions visibles dans les pixels du MP4 (non uniquement décrites dans JSON ou prompts).
5. Synchronisation des dialogues mesurée et contrôlée ; signaler honnêtement les limites de lip-sync.
6. Prévisualisation, erreurs de génération compréhensibles, régénération ciblée d'un plan.
7. Isolation des organisations, contrôle des crédits, plafonds de coût, relances bornées.
8. Aucun impact non validé sur Standard et Quiz.

## Scénario de référence : Influence mentale
Prototype cible : 15 à 30 secondes, format 9:16, trois plans.
- Plan 1 : A parle, bouge les lèvres et fait un geste ; B écoute et réagit.
- Plan 2 : A se penche et change d'expression ; cadrage plus serré ; B hésite.
- Plan 3 : B recule et répond avec émotion ; continuité des vêtements, traits et décor.
Critères de refus : images fixes, zooms sur photos, visages qui changent d'identité, paroles attribuées au mauvais personnage, absence d'action observable. Validation : regarder le MP4 avec audio, mesurer les coûts et documenter les échecs.

## Audit vérifié : AiAddicts
- `growthos/engine/story_compile.py` : `compile_story` convertit chaque shot en bloc `text`, `voice_id`, `speaker_id` et `visual` illustré. `estimate` compte une image par shot. Ce n'est pas un contrat de clip animé.
- `growthos/engine/script.py` : `normalize_script` appelle `story_compile.compile_story(quiz.compile_quiz(data))`. Le commentaire dans `story_compile.py` disant que ce module n'est pas raccordé est donc obsolète sur la branche lue.
- `growthos/engine/story_intelligence/validator.py` : valide durée, personnages, locuteurs et dialogues, sans actions, expressions ni mouvements de caméra.
- `growthos/engine/story_intelligence/timing.py` : aligne des durées audio fournies par l'appelant, sans mesurer directement l'audio ni générer de vidéo.
- `docs/product/story-intelligence-pilot-v02.md` : décrit un pilote de timing hors ligne, non un pipeline animé abouti.
Ces observations ne démontrent pas l'absence de fournisseurs vidéo ailleurs dans le dépôt. Inventaire global restant.

## Audit vérifié : growthos-web
- `docs/product/STORY_STUDIO_VISION.md` : affirme que Story Studio est un espace de réalisation, non un simple formulaire ; distingue vision et fonctionnalités livrées.
- `src/lib/story-studio/storyboard.ts` : type `Shot` = id, speaker_id, dialogue, duration_s ; aucune action/caméra/asset animé.
- `src/lib/story-studio/render.ts` : estimation images par scène, plafond 12 plans et 3 tentatives.
- `src/app/(app)/story-studio/ai-actions.ts` : `proposeStoryPlan` demande explicitement une 'illustrated dialogue story' et des scènes à un locuteur. Cela favorise un storyboard narré, pas une scène d'interaction.
- `src/app/(app)/story-studio/story-editor.tsx` : parcours project / characters / storyboard / preview ; prévisualisation de données, pas preuve de clip animé.
- `src/app/(app)/story-studio/actions.ts` : sauvegarde en `content_items`, queue conditionnée par `STORY_GENERATION_ENABLED`, droits admin, consentement payant, vérifications de modération et crédits. Ces protections sont utiles mais leur efficacité en exécution n'est pas auditée ici.
- `src/app/(app)/story-studio/page.tsx` : l'accès à la génération reste sous contrôle serveur.

## Diagnostic
Le contrat actuel privilégie image+voix par plan. Le problème principal est une inadéquation produit/contrat, pas un manque de polish UI. Une partie du pipeline Story est raccordée à la normalisation, mais l'animation réelle reste non démontrée. Ne pas déduire la disponibilité de vidéo animée de tests verts ou d'un statut `queued`.

## Architecture cible (à valider, non implémentée)
Idea -> NarrativePlan -> CharacterBible (références visuelles et voix) -> ShotPlan (actions, émotions, caméra, décor, dialogue, durée) -> AnimatedClip (source, provenance, durée, coût, état de vérification) -> AudioTracks -> QC -> FinalMP4.
Isoler Story du pipeline Standard/Quiz ; adapter les fournisseurs derrière une interface ; ne pas imposer de nouveaux services sans besoin prouvé. Assurer traçabilité des versions d'assets, sécurité multi-tenant, idempotence, plafonds de dépense et régénération par plan.

## Étapes, livrables et décisions
- G0 Cadrage : validation de cette vision et du test Influence mentale.
- G1 Audit exhaustif : inventaire des workers, fournisseurs texte/image/vidéo, audio, stockage, jobs, coûts, limites, tests et déploiement des deux dépôts. Livrable : cartographie avec chemins et preuves.
- G2 Faisabilité : comparaison technique et financière de fournisseurs d'animation, qualité d'identité, interactions, lip-sync, disponibilité et coûts par seconde acceptée. Aucun appel payant sans accord.
- G3 Spike isolé : produire et visionner une scène animée, mesurer taux d'échec, coût et latence ; GO/NO-GO.
- G4 Contrats et architecture : schémas versionnés, validation, queue, budget, sécurité et interfaces de fournisseurs ; revue avant code.
- G5 MVP backend : génération réelle, assemblage, stockage, QC, tests et protection Standard/Quiz.
- G6 Studio UX : contrôles réalisateur, preview 9:16, états de progression, édition/régénération.
- G7 Stabilisation : tests de bout en bout, régressions, sécurité, coûts, qualité et décision de lancement.

## Risques et contrôles
- Identité changeante -> références réutilisées, revue visuelle entre plans.
- Vidéo figée -> inspection des mouvements dans le MP4.
- Voix/lèvres incohérentes -> mesure et vérification audio/vidéo.
- Coûts élevés -> plafonds, confirmation explicite, régénération ciblée, suivi coût par seconde acceptée.
- Verrouillage fournisseur -> adaptateur indépendant et provenance.
- Régressions -> branches isolées, fixtures et tests Standard/Quiz.
- Jobs bloqués -> délais, relances bornées, idempotence, observabilité.
- Accès inter-organisations -> contrôles côté serveur et tests d'isolation.

## Limites de cet audit
Lecture ciblée des fichiers nommés, pas exploration exhaustive du dépôt, pas d'exécution locale ni tests end-to-end, pas de génération payante, pas de vérification d'artefacts MP4. Les coûts et délais restent à chiffrer à G1-G2. Aucun code ni configuration de production ne doit être modifié sur la base de ce document seul.

## Gouvernance
Chaque étape a un propriétaire, des preuves, des critères d'acceptation et une décision GO/NO-GO. Les PR ne sont pas des preuves de valeur produit. Ne jamais déclarer Story Studio animé sans MP4 vérifié. Aucune fusion, dépense API ou activation production sans validation explicite.
