# Opus 5.5, motions et UGC : ce que Faceloop peut en tirer (2026-10-10)

Recherche web, sans code. Sources : témoignages de créateurs et blogs d'éditeurs d'outils, non reproduits ici.

## 1. Comment Opus 5.5 fait des motions

- Il n'a pas de génération vidéo : il écrit un programme HTML (canvas/SVG) qui expose `window.seek(t)`. Chaque image est une fonction pure de `t` (pas de `Date.now`, `requestAnimationFrame`, `Math.random` non seedé, transitions CSS).
- Rendu séparé : Playwright capture une image par pas, ffmpeg encode (H.264, CRF 16-18), l'audio est ajouté en seconde passe, les films longs sont rendus par scène puis concaténés.
- Le harnais pèse plus que le prompt : règles maison (`CLAUDE.md`), vrais assets de marque, guide de style extrait d'une référence, beat sheet horodaté validé avant de coder, ressorts amortis, grille sonore mesurée (librosa), normalisation -14 LUFS.
- Boucle de critique : planche contact (une image par temps fort) + aperçu taille téléphone, note sur 7 critères (accroche, lisibilité, mouvement, variété, composition, marque, synchro son), correction des 3 pires défauts, re-rendu des seules secondes touchées, répéter jusqu'à 8/10.
- Limites connues : débordements, texte illisible, timing faux, rendu « diaporama animé ». Les démos sont des galeries choisies.

Sources : huggingface.co/blog/karmen-beatapi/how-to-make-videos-with-claude-opus-5-5, movez.substack.com/p/how-to-build-motion-design-studio, friction.com.my/insights/claude-opus-5-5-motion-design.

## 2. UGC (hors Opus)

Aucune source ne montre de l'UGC fait par Opus. Les guides 2026 d'UGC IA convergent sur : accroche (0-3 s) / problème / démo / appel à l'action ; règle « 90/10 » (b-roll 90 %, avatar par salves) ; sous-titres obligatoires ; matrice de test 3-5 accroches × 2 acteurs. Chiffres = conventions de vendeurs, pas des mesures.

Sources : admove.ai/blog/how-to-create-ugc-ads, prizmad.com/guides/how-to-make-ai-ugc-ads, fliki.ai/blog/how-to-create-ugc-style-ads-with-ai-avatars.

## 3. Écart avec Faceloop (état du dépôt)

- Existe : contrôle qualité vision **par image** (`engine/image_quality_control.py`, opt-in, `IMAGE_QC_ENABLED`), score éditorial du script (`editorial_quality.py`), score de génération (`quality.py`), aperçu de scène (`motion_graphics/preview.py`), mesure de synchro voix/visuel (audit du 10/10, outil hors dépôt).
- N'existe pas : critique visuelle **de la vidéo rendue** (planche contact + note + re-rendu ciblé).

## 4. Pistes, par ordre de valeur

1. **Critique de la vidéo rendue** (détail § 5).
2. **Règles de motion explicites** (nouvel élément toutes les 2-4 s, un accent, liste de défauts interdits) injectées dans la planification de scène : coût nul, répond au risque « diaporama ».
3. **Ressorts amortis** dans les rendus Pillow/Manim : gain surtout cosmétique.
4. **Variantes d'accroche A/B** sur un même corps de script, branchées sur la boucle d'apprentissage.
5. **Assets de marque réels** : seulement si un format « pub produit » est ouvert.

À éviter : un second moteur `seek(t)` HTML/Playwright (Faceloop est déjà déterministe) ; promettre un avatar UGC réaliste (autre technologie, autres coûts).

## 5. Piste 1 : cadrage

- **Entrée** : MP4 final + scènes + mots horodatés. **Sortie** : une planche contact (≈ 12 images aux temps forts), une note par critère, une liste de scènes faibles avec horodatage.
- **Critères** : reprendre ceux de la grille ci-dessus, en ajoutant lisibilité mobile et débordement de texte. Les critères mesurables sans LLM (synchro, débordement, durée de présence du texte) passent par le code ; le LLM ne juge que ce qui est subjectif.
- **Action** : `quality_check` existant (pas de blocage dur au début) ; re-rendu ciblé de la scène seulement dans un second temps.
- **Coût (estimation, non mesurée)** : un appel vision sur une image composite, de l'ordre de quelques centimes, contre ≈ 0,34-0,37 $ mesuré par vidéo. À mesurer sur 5 vidéos avant d'activer.
- **Risque** : un juge LLM bruité qui note faux. Mitigation : commencer en mode observation (noter sans agir), comparer aux vues réelles et à ton avis sur ~10 vidéos, puis seulement agir.
- **Pas de changement de schéma** pour la phase d'observation si le résultat est stocké dans les métriques existantes (à vérifier).

## 6. Limites de cette recherche

Témoignages non reproduits ; une page (pasqualepillitteri.it) illisible ; aucune source UGC propre à Opus ; aucun essai sur nos vidéos.

## 7. Résultat de la validation (2026-10-10)

Outils : `scripts/video_critique.py` (juge LLM sur planche contact, ≈ 0,003 $/vidéo estimé, bruit ±1-2 points par critère) et `scripts/motion_metrics.py` (mesures par le code). Croisement avec `content_performance` : 33 vidéos publiées, ≥ 100 vues, dernière valeur de `watch_time_pct`.

| Mesure | rho avec `watch_time_pct` | IC 95 % |
|---|---|---|
| activité moyenne | −0,17 | −0,49 ; +0,18 |
| part d'images figées | −0,23 | −0,54 ; +0,13 |
| plus longue pause | −0,24 | −0,56 ; +0,09 |
| activité des 3 premières secondes | +0,36 | 0,00 ; +0,64 |
| durée | +0,57 | +0,24 ; +0,80 |

Aucun lien démontré entre mouvement et rétention. Échantillon mal adapté : 20 vidéos `gta_loading`, 3 `motion_graphics`, durées 43-156 s (nos vidéos récentes : 20-27 s). La durée corrèle surtout entre comptes (rho par compte : +0,68 sur 16 vidéos, +0,10 sur 9) : confusion probable, non interprétable. Décision : pas de critique automatique branchée au pipeline ; refaire le test avec 30-50 vidéos courtes / motion graphics avec métriques.
