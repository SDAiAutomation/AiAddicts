"""Style visuel « Explainer animé » : un film procédural rendu dans Chromium (voir docs/explainer-plan.md).

Vit à côté de `engine/motion_graphics/` (Pillow/Manim) sans le remplacer.
"""

# Version du runtime JS figé (runtime/*.js). Fait partie de la clé de cache d'un plan rendu : à incrémenter
# à chaque changement de comportement du runtime.
RUNTIME_VERSION = "0.1.0"
