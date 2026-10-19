---
name: explainer-and-moderation
description: État de l'Explainer animé (bêta admin) et des garde-fous avant la voix après l'avertissement ElevenLabs du 2026-10-19
metadata:
  type: project
---

**Explainer (admin seulement).** Accès vérifié par le site ET par le worker (`engine/explainer/access.py`, auteur dans `ADMIN_USER_IDS`, échec fermé, avant le crédit). Une première vidéo réelle a coûté environ 0,20 $ de LLM (un seul échantillon, mesures dans `generation_cost_report.explainer`, lisibles avec `scripts/explainer_measures.py`). La durée d'installation de Chromium sur le runner n'est pas mesurée. Les bruitages ont été remontés (#49) ; le niveau reste à confirmer à l'oreille et se règle par `EXPLAINER_SFX_GAIN` / `EXPLAINER_SFX_DUCK_RATIO`.

**Avant la voix (ordre dans `assembler.run_for_content_item`).** `moderation.check_script` (OpenAI, gratuit, catégories graves seulement) → couche Claude Haiku contre fraude/usurpation/faux avis/harcèlement (#50) → `moderation.check_integrity` : défauts bloquants déterministes de `retention.BLOCKING_CODES` (#51) → crédit. Avant #51, ces défauts n'étaient vus qu'après la synthèse vocale.

**Contexte.** ElevenLabs a averti d'un contenu « Fraudulent, predatory, or abusive behavior » sans citer le texte. Le suspect probable, non confirmé, est une série finance (CTA « comment 'start' »). Ces contrôles sont des garde-fous, pas une garantie de conformité : le filtre du fournisseur est opaque.

**Réglages.** `MODERATION_ENABLED`, `MODERATION_FAIL_CLOSED`, `FRAUD_CHECK_ENABLED`, `FRAUD_CHECK_MODEL`, `INTEGRITY_PRECHECK`. Le coût du contrôle Haiku n'est pas mesuré.
