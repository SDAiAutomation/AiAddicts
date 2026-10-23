# Story Studio — décisions produit et reprise (24 octobre 2026)

## Décisions confirmées
- Faceloop Story Studio produit des **histoires réellement animées**, pas des images statiques avec zoom et narration.
- Personnages pilotes : **Néo, jeune renard**, et **Orion, vieux hibou** ; animaux anthropomorphes parlant, marchant, exprimant des émotions et interagissant. Le produit ne sera pas limité à ces deux personnages.
- Principe directeur : **faire plus avec moins**. Un appel IA structuré pour le scénario et la planification des scènes (personnages, dialogues, actions, émotions, cadrages, timings) ; puis validation, orchestration et animation **déterministes**. Éviter une IA vidéo coûteuse pour chaque scène.
- **Choix MVP : animation 2D avec personnages riggés**, assets et mouvements réutilisables. La 3D reste une évolution possible, pas la cible MVP.
- Moteur 2D définitif **non choisi** : comparer Rive / moteur 2D adapté et Blender Grease Pencil selon scripting, export, licences, intégration Python, qualité et coûts. Ne pas présenter un outil comme décidé sans benchmark.
- Stack candidate : Next.js/React/TypeScript (UI existante), Python GrowthOS (scénario, validation et orchestration), bibliothèque d'assets 2D (personnages, rigs, décors, poses, animations), ElevenLabs (voix avec cache), FFmpeg (assemblage), Supabase (projets et stockage), Vercel (frontend). Ne pas ajouter Redis/Kubernetes/GPU dédié sans nécessité démontrée.
- Story Intelligence doit produire un contrat versionné indépendant du moteur d'animation : personnages, actions, émotions, poses, caméra, dialogue, temps, assets et contraintes de continuité.
- Test de validation : **Influence mentale**, 15–30 s, 9:16, au moins trois plans, Néo et Orion. Actions visibles, échanges, réactions, voix cohérentes, continuité d'apparence. Livrable : MP4 réel, pas storyboard/JSON.
- Limite assumée : l'animation déterministe est bornée par les rigs, poses et mouvements disponibles ; pas de promesse de génération arbitraire de n'importe quelle action.
- Protéger les formats Standard et Quiz, isolation multi-tenant, budgets et quotas, idempotence et observabilité.

## Gouvernance
- Approche **Plan complet** validée : cadrage et audit des deux dépôts avant implémentation.
- Aucun changement de code, nouvelle PR, fusion, déploiement ou appel API payant sans autorisation spécifique.
- Documents conservés sur GitHub, pas de livrables locaux comme source de vérité.
- Audit initial dans `docs/product/STORY_STUDIO_CADRAGE_AUDIT_2026-10-24.md` sur cette branche. Cet audit est **partiel**, pas exhaustif.
- Attention : `story_compile.py` décrit un branchement absent dans son commentaire, mais `script.py` appelle déjà `story_compile.compile_story`. Vérifier les comportements, pas seulement les commentaires.

## Travail à reprendre demain (sans écrire de code)
1. Inventaire exhaustif des workers, contrats, stockage, files d'attente, intégrations, sécurité, tests et flux Story des deux dépôts.
2. Matrice comparative **2D riggée** : Rive, Blender Grease Pencil et alternatives appropriées, en particulier automatisation, animation des dialogues, réutilisation, licence et export.
3. Spécification de Character Bible et ShotPlan JSON versionnés, et de l'interface entre IA (une génération structurée) et moteur déterministe.
4. Définir bibliothèque minimale de Néo et Orion (expressions, bouche, marche, regard, gestes), décors et trois plans du pilote.
5. Budget initial et coût marginal par vidéo, dépendances, risques, jalons GO/NO-GO, critères mesurables.
6. Soumettre la décision d'architecture à l'utilisateur **avant toute implémentation**.

## À ne pas oublier
Le choix 2D riggée est une orientation produit MVP, **pas** une preuve de faisabilité technique. Ne pas revenir à une architecture de génération vidéo IA par plan sans nouvelle discussion et accord.
