# Story Studio — inventaire complet de reprise et transfert à Claude
Date : 2026-10-24. **Ce fichier est versionné ; les MP4 et images binaires sont dans la bibliothèque ChatGPT, pas dans GitHub.**

## Documents et commits déjà sur GitHub
Branche `docs/story-studio-animation-recovery`, PR #71 :
- `docs/product/STORY_STUDIO_CLAUDE_HANDOFF_2026-10-24.md` — contexte, décisions, risques, NO-GO artistique.
- `docs/product/STORY_STUDIO_MASTER_PLAN.md` — phases, gates et définition de terminé.
- `docs/product/CLAUDE_CODE_STORY_STUDIO_PROMPT.md` — prompt d'exécution.
- `docs/product/STORY_STUDIO_STEP_01_GENERATION_PATH_2026-10-24.md` — chemin génération.
- `docs/product/STORY_STUDIO_STEP_02_SECURITY_STORAGE_AUDIT_2026-10-24.md` — worker, crédits, stockage.
- `docs/product/STORY_STUDIO_STEP_03_ARCHITECTURE_2026-10-24.md` — architecture proposée.
- `docs/product/STORY_STUDIO_STEP_04_OFFLINE_PROTOTYPE_2026-10-24.md` — démonstration rejetée.
- Autres `STORY_STUDIO_*` sur la branche : audits, manifestes et contrats.

Branche `feat/story-studio-offline-animation-spike`, PR #72 :
- `growthos/engine/story_animation_spike/timeline.py`
- `growthos/engine/story_animation_spike/render_demo.py`
- `growthos/engine/story_animation_spike/test_timeline.py`
- `growthos/engine/story_animation_spike/test_render_demo.py`
- `.github/workflows/story-animation-offline-spike.yml`
- Ce code est **un spike technique non validé visuellement**. Ne pas fusionner comme renderer produit.

Frontend à conserver : `SDAiAutomation/growthos-web`, fichiers Story Studio dans `src/app/(app)/story-studio/` et `src/lib/story-studio/`.

## Assets réellement disponibles dans la bibliothèque ChatGPT
Dossier : `/Faceloop/Story Studio/References/`.
- `Te-voila-case_reference.mp4` — 71 167 276 octets.
- `C-est-garanti_reference.mp4` — 56 161 187 octets.
- `story_video_contact_sheet.jpg` — 113 681 octets.
Ces fichiers ne sont **pas** dans le dépôt GitHub. Ils doivent être remis à Claude via un dossier local ou un dépôt d'assets privé approprié. Ne pas confondre cette image contact sheet avec des concept arts/rigs de qualité : elle sert seulement à consulter les références.

## Autres sorties locales non versionnées
- Prototype `neo_orion_offline.mp4`, 9,5 s, 540x960, silencieux, visuellement rejeté.
- `offline_animation_poc.py`, script Python local de la première démonstration.
- Aperçu GIF `neo_orion_preview.gif` et copie MP4 `neo_orion_demo.mp4` produits pour consultation. Ces éléments sont des **contre-exemples**, pas des références qualité.
- Ne pas affirmer qu'il existe déjà une bibliothèque d'assets professionnels, des rigs Néo/Orion ou une animation professionnelle : ils restent à produire.

## Transfert sûr recommandé
1. Fournir à Claude un dossier local contenant les deux MP4 et le contact sheet. Vérifier droits d'usage et confidentialité avant un push.
2. Pour stockage GitHub, privilégier un dépôt **privé** et Git LFS pour les MP4, avec `.gitattributes` ; ne pas committer des binaires vidéo lourds dans l'historique Git normal.
3. Ne jamais mettre des vidéos de tiers dans le code produit ni dans des assets commercialisés.
4. Ajouter dans ce dossier un README expliquant que ces fichiers sont des **références**, pas des assets de production.
5. Faire analyser les MP4 effectivement par Claude, puis lancer Gate 0. Sans visionnage, aucun choix d'architecture définitif.

## État de la reprise
- Audits : écrits et versionnés.
- Prototype local : réalisé mais refusé pour qualité.
- Prototype code sur GitHub : oui, PR #72 en brouillon.
- Références vidéo sur GitHub : non.
- Rig/animation professionnelle : non.
- Validation CI/E2E production : non démontrée.
- Décision : priorité absolue à la fidélité visuelle aux références et à la validation utilisateur.
