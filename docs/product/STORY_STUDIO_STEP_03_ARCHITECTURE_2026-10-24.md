# Story Studio — étape 3 : architecture de reconstruction proposée

Date : 2026-10-24. Statut : conception basée sur lecture statique, **pas encore implémentée**.

## 1. Point de départ réel
Frontend `growthos-web` : éditeur Story, génération de dialogues illustrés, validations et sauvegarde. Backend `AiAddicts` : worker partagé, `story_compile`, TTS, visuels, FFmpeg, stockage, crédit et tests offline. Le premier E2E Story n'a pas été réalisé selon `STORY_STUDIO_FIRST_RENDER.md`.

## 2. Architecture cible à coût borné
```text
Story Studio UI (brouillon et personnages existants)
  -> NarrativePlan v2 (dialogue, intention, émotion)
  -> ShotPlan v1 strict (rig, action, caméra, temps, asset IDs)
  -> Validation Python/TS + catalogue d'assets autorisés
  -> Audio TTS existant ou fixtures offline
  -> Recalage temporel sur audio décodé
  -> StoryAnimationRenderer (interface versionnée)
       -> OfflineRigRenderer (spike isolé, moteur à sélectionner)
       -> sortie clips locaux + manifeste + métriques
  -> FFmpeg / contrôles qualité
  -> stockage privé/versionné existant, après vérification
```
Un seul appel de planification IA si nécessaire ; animation déterministe à partir de rigs réutilisables. Pas de GPU ni d'API vidéo payante exigée au départ.

## 3. Frontières de compatibilité
- Garder `content_format=story` historique et son compilateur pour les brouillons existants.
- Nouveau champ de contrat `animation_schema_version=1` et chemin de rendu **explicitement opt-in**, désactivé par défaut. Ne pas réinterpréter les vieux scripts.
- Le nouveau renderer doit être un module distinct de `visuals.py` et des branches Standard/Quiz. Aucun import cyclique dans `assembler.py`.
- Préserver la file, les crédits, les événements, les quotas et la version de vidéo ; adapter seulement l'étape visuelle sous contrôle.
- Pas de migration de données obligatoire pour un spike offline ; ne pas ajouter de nouvelles colonnes sans preuve de nécessité.

## 4. Contrat renderer minimal
```python
class StoryAnimationRenderer(Protocol):
    def render(self, plan: dict, asset_manifest: dict, output_dir: str) -> dict:
        # returns {"clips": [...], "duration_ms": int, "metrics": {...},
        #          "renderer_version": str, "asset_hashes": {...}}
        ...
```
Entrées contrôlées : aucun chemin arbitraire provenant de l'IA ; assets résolus côté serveur ; nombre d'acteurs et durée plafonnés ; vérification que chaque action existe. Sortie : clips sans voix puis assemblage audio ; lip-sync sur timings mesurés.

## 5. Critères de benchmark
Même scène Néo/Orion pour Godot, Blender et Rive si possible : rendu sans UI, reproductible, 9:16, 30 fps, deux personnages, mouvement du corps, bouche synchronisée, gestes, caméra et décors. Mesurer coût total par minute, CPU/RAM, dépendances, licence, temps de développement et fiabilité. Godot reste candidat, pas décision définitive.

## 6. Nouveaux constats sécurité et confidentialité
- La migration initiale `20260904110000_content_videos_bucket.sql` créait `content-videos` avec `public=true`. `20260919161000_content_videos_allow_jpeg_posters.sql` conserve alors sa visibilité.
- `growthos/scripts/activate_private_generate.py` prévoit explicitement une **activation privée séparée**, via Storage API, uniquement après vérification web+worker. Sa présence **ne prouve pas** que cette activation a eu lieu.
- `storage.py` utilise `get_public_url` comme référence et suppose que le site contrôle l'accès à un bucket privé. **Vérifier l'état réel du bucket avant tout lancement**.
- `content_assets` est distinct : la migration `20261003140000_content_assets.sql` crée son propre bucket privé.
- Le mécanisme `upsert=true` mérite un test d'immutabilité des versions.
- L'historique CI n'a pas pu être interrogé via le connecteur dans cette passe : statut des tests **inconnu**, ne pas déclarer vert.

## 7. Plan séquentiel de développement
1. Vérifier configuration effective Supabase (lecture seule) et accès médias, runs CI, contrats des jobs.
2. Choisir moteur sur spike hors ligne avec assets originaux simples, aucune API payante.
3. Ajouter validateur `ShotPlan` et fixtures croisées Python/TypeScript.
4. Construire rig Néo/Orion, trois scènes, animation, visèmes et export MP4.
5. Mesurer qualité et coût ; GO/NO-GO.
6. Brancher renderer via feature flag dédié, sans casser l'ancien mode.
7. UI Story Studio, previews, tests tenant, quotas, crédits, versions et E2E.

## 8. Décision
**GO pour un prototype offline isolé après validation du moteur et du périmètre. NO-GO pour l'activation du rendu Story en production tant que la confidentialité effective et les tests E2E ne sont pas vérifiés.**

Aucun code ni déploiement modifié dans cette étape.
