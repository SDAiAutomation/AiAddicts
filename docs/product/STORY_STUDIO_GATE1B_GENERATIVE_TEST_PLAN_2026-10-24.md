# Story Studio — Gate 1B : art généré par l'API OpenAI déjà dans Faceloop + animation locale (révisé)

Date : 2026-10-24. Statut : **plan, rien d'exécuté, 0 € dépensé**. Remplace la version « image→vidéo par fournisseur externe », écartée par l'utilisateur (pas de service dépendant supplémentaire).

## Décision
Le rig par code plafonnait à cause du **dessin**, pas du moteur d'animation. On garde l'animation **locale** (Godot, gratuit, déjà installé) et on remplace le dessin par des **illustrations générées avec l'API OpenAI déjà utilisée par Faceloop** (`growthos/engine/openai_images.py`, routeur `image_model_router.py`, bible de personnage `image_character_bible.py`). Aucun nouveau fournisseur, aucune vidéo générée, rendu final à coût marginal ≈ 0.

## Pipeline du test
1. **Fiche de personnage** : 1 personnage original (style cartoon années 1930 N&B + accent rouge), vues face / 3/4 / plein pied, fond uni.
2. **Pièces détachables** : tête, corps, bras, jambes, mains, yeux/bouches (plusieurs formes) générés ou découpés sur fond uni, puis détourés localement (FFmpeg/Python, sans service).
3. **Décors** : 2 décors en 3 couches (fond, milieu, avant-plan) pour la parallaxe.
4. **Animation** : marionnette 2.5D dans Godot (os, déformation, visèmes, caméra, grain), même chaîne que Gate 1.
5. **Sortie** : clip de 5-8 s, 9:16, jugé visuellement.

## Budget et coût
- Table de coûts du dépôt (estimations internes, non vérifiées en direct) : `gpt-image-1-mini` ≈ 0,015 $ (low) / 0,03 $ (medium) par image ; `gpt-image-1` ≈ 0,05 / 0,10 / 0,19 $.
- Test : 30 à 40 images (itérations comprises) ⇒ **≈ 1 à 4 $ [ESTIMATION]**. **Plafond : 5 USD**, journal de coût par image, arrêt au plafond.
- Brouillons en qualité `low`, versions finales seulement après validation.

## Prérequis sécurité
La clé `OPENAI_API_KEY` n'existe que dans les secrets GitHub (non lisibles). Elle ne sera ni demandée dans le chat ni committée : l'utilisateur la place lui-même dans une variable d'environnement locale pour la session. Les images générées restent hors Git tant que non validées ; aucune donnée utilisateur n'est envoyée.

## Critère de décision
GO si : personnage reconnaissable sur ≥ 3 poses/plans, pièces propres à détourer, animation visuellement supérieure au Gate 1. Sinon NO-GO et retour à la discussion (illustrateur humain pour les assets).

## Droits
Vérifier les conditions d'usage commercial d'OpenAI pour les sorties d'image (déjà utilisées en production par Faceloop) ; ne jamais fournir de référence protégée en entrée.
