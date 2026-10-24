# Story Studio — contrat d'animation v1 et plan d'exécution

Date : 2026-10-24
Statut : **proposition technique à valider ; aucun moteur animé implémenté**.
Source : audit ciblé des fichiers `AiAddicts/growthos/engine/story_compile.py`, `AiAddicts/growthos/engine/story_intelligence/validator.py`, `growthos-web/src/lib/story-studio/storyboard.ts`, `growthos-web/src/lib/story-studio/render.ts`.

## Constats vérifiés
- Le compilateur Story actuel convertit chaque plan en bloc texte + voix + visuel illustré ; `estimate` compte une image par plan.
- Le validateur Python accepte personnages, locuteur, dialogue, durée et IDs ; aucun geste, émotion, décor, rig, mouvement ou caméra.
- Le type TypeScript `Shot` est limité à `id, speaker_id, dialogue, duration_s`.
- Incohérence d'interface : `MAX_SHOTS=30` dans le storyboard ; `MAX_RENDER_SHOTS=12` côté rendu et backend.
- Les deux validations (Python/TS) devront être alignées par fixtures partagées avant tout branchement.

## Objectif du contrat
Transformer un scénario en instructions **bornées, explicites, validables et déterministes**, indépendantes du moteur 2D. Ne pas demander à un moteur de créer arbitrairement une action absente de sa bibliothèque.

## Exemple de ShotPlan JSON v1 (proposé, non exécutable actuellement)
```json
{
  "schema_version": "story_animation_v1",
  "project_id": "pilot_influence_mentale",
  "aspect_ratio": "9:16",
  "fps": 30,
  "target_duration_ms": 21000,
  "character_bible": [
    {"id":"neo","rig_asset_id":"fox_neo_v1","voice_id":"voice_neo","design_version":"1"},
    {"id":"orion","rig_asset_id":"owl_orion_v1","voice_id":"voice_orion","design_version":"1"}
  ],
  "shots": [
    {
      "id":"s1","duration_ms":7000,"scene_asset_id":"forest_clearing_v1",
      "camera":{"preset":"medium_two_shot","motion":"static"},
      "actors":[
        {"character_id":"neo","position":"left","facing":"right","expression":"curious",
         "actions":[{"name":"walk_in","start_ms":0,"duration_ms":1800},{"name":"talk_gesture","start_ms":2000,"duration_ms":2500}]},
        {"character_id":"orion","position":"right","facing":"left","expression":"neutral",
         "actions":[{"name":"listen_nod","start_ms":3200,"duration_ms":900}]}
      ],
      "dialogue":[{"speaker_id":"neo","text":"Pourquoi certaines personnes sont-elles toujours gentilles avec moi ?","start_ms":1900,"end_ms":6500}]
    },
    {
      "id":"s2","duration_ms":7000,"scene_asset_id":"forest_clearing_v1",
      "camera":{"preset":"medium_orion","motion":"slow_push"},
      "actors":[
        {"character_id":"orion","position":"center","facing":"left","expression":"serious","actions":[{"name":"wing_explain","start_ms":900,"duration_ms":3500}]},
        {"character_id":"neo","position":"left_edge","facing":"right","expression":"surprised","actions":[{"name":"react_surprise","start_ms":4600,"duration_ms":900}]}
      ],
      "dialogue":[{"speaker_id":"orion","text":"Parfois, elles veulent simplement obtenir quelque chose.","start_ms":900,"end_ms":5300}]
    },
    {
      "id":"s3","duration_ms":7000,"scene_asset_id":"forest_clearing_v1",
      "camera":{"preset":"medium_neo","motion":"static"},
      "actors":[
        {"character_id":"neo","position":"center","facing":"right","expression":"worried","actions":[{"name":"step_back","start_ms":500,"duration_ms":1100}]},
        {"character_id":"orion","position":"right_edge","facing":"left","expression":"neutral","actions":[{"name":"listen_nod","start_ms":3800,"duration_ms":700}]}
      ],
      "dialogue":[{"speaker_id":"neo","text":"Alors, comment reconnaître une vraie amitié ?","start_ms":1700,"end_ms":5500}]
    }
  ]
}
```

Les IDs de rigs, voix, décors et actions ci-dessus sont **fictifs** et doivent être résolus par un registre d'assets réel. Les temps sont des intentions initiales : recalage sur les durées audio mesurées obligatoire avant rendu. Ne pas affirmer que ces mouvements sont déjà disponibles.

## Règles de validation proposées
1. Schéma versionné strict ; rejeter champs inattendus ou inconnus aux frontières d'exécution.
2. Durées entières positives, fin de chaque action et dialogue <= durée du plan ; durée globale = somme des plans.
3. Unicité des IDs ; toute référence personnage/rig/voix/décor/action doit exister dans un catalogue autorisé et accessible au tenant.
4. Enum contrôlées pour caméra, positions, expressions et mouvements ; aucune commande arbitraire, aucun chemin de fichier fourni par l'IA.
5. Limiter nombre de plans, acteurs par plan, dialogues, durée et taille JSON selon budgets configurés ; séparer limites de brouillon et de rendu.
6. Pas de chevauchement de dialogues par défaut ; gestion explicite de la prise de parole et du lip-sync.
7. Identité visuelle, voix et versions d'assets immuables pendant un rendu.
8. Contrat d'animation indépendant de `story_compile.py` historique ; routage explicite, feature flag désactivé par défaut.
9. Rendu reproductible avec version moteur, manifest d'assets, hash ShotPlan et graine de variations enregistrés.
10. Isolation multi-tenant, autorisation côté serveur, idempotence, quotas, retry borné, coûts et métriques par plan.

## Benchmark : protocole identique pour chaque moteur
- Candidats : Godot, Blender, Rive ; Godot favori provisoire uniquement.
- Entrée : même ShotPlan simplifié, mêmes rigs/décors, même voix test.
- Sortie : trois clips animés + MP4 9:16, sans intervention manuelle pendant le rendu.
- Mesures : présence de mouvements corporels, lip-sync, cohérence inter-plans, qualité, temps de rendu, consommation mémoire, complexité de packaging, coût/licence, maintenabilité.
- GO si deux personnages interagissent dans au moins trois plans avec mouvements visibles et export reproductible ; sinon NO-GO et ajustement du périmètre.

## Plan d'implémentation conditionnel
A. Terminer l'audit complet des deux dépôts et leurs tests, workers, permissions et stockage (lecture seule).
B. Choisir moteur après benchmark et autorisation de spike isolé.
C. Implémenter catalogue d'assets et rig Néo/Orion avec actions minimales.
D. Ajouter parseur/validateur Python + TypeScript et fixtures communes, tests adversariaux.
E. Adapter le renderer derrière une interface, garder Story historique et Standard/Quiz intacts.
F. Synchroniser voix/visèmes, FFmpeg, QA pixels/audio et stockage.
G. Brancher l'UI Studio, preview et régénération ciblée.
H. Tests end-to-end, coûts, isolation, régressions, décision de lancement.

## Gouvernance
Ce fichier est une **spécification**, pas un résultat d'exécution. Ne pas fusionner, déployer ou déclencher de dépenses sans décision explicite. Le vrai livrable du spike est un MP4 inspecté, pas seulement du JSON ou des tests unitaires.
