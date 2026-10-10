# Script Engine : `reasoning_effort` low contre medium (2026-10-11)

Même banc que `script-first-pass-length-2026-10-10.md` (10 sujets × 6 répétitions = 60 générations par série, `gpt-5-mini`, code de `master` après les PR #57, #58, #61 ; prompt et retries inchangés). Seul `reasoning_effort` du premier appel change (variable d'expérience locale, branche non poussée `experiment/script-reasoning-effort-20261010`).

| | low (actuel) | medium |
|---|---|---|
| Réussite 1re tentative | 1/60 = 2 % | 6/60 = 10 % |
| Réussite définitive | 46/60 = 77 % [65-86] | 38/60 = 63 % [51-74] |
| Échecs | 12 longueur + 2 plans | **22 délais dépassés (45 s)**, 0 longueur |
| Appels moyens | 1,98 | 1,18 (appels interrompus par le délai) |
| Durée moyenne d'une génération | 22 s (max 31) | 56 s (max 82) |
| Mots 1er essai (médiane) | 149 | 160 |
| 1er essai sous 206 mots | 59/60 | 33/39 terminés |
| Mots par bloc point | 17,3 | 19,5 |
| Jetons sortie par succès | 3 472 | 10 874 |
| Coût estimé par script réussi | 0,0128 $ | 0,0393 $ (×3) |

Lecture :
- `medium` ne règle pas la première tentative (85 % encore sous le minimum) ; il augmente la longueur par bloc (19,5 contre 17,3) sans l'amener à 24.
- Parmi les 38 générations terminées, les 38 réussissent (retry efficace), mais **22 sur 60 dépassent le délai de 45 s** du serveur : à ce réglage, medium fait échouer plus de scripts qu'il n'en sauve.
- Coût ×3 et durée ×2,5 : NO-GO pour le chemin standard. Non testé : `medium` seulement sur la relance (avec un délai relevé).
- Limites : 60 générations par série, un modèle, un profil ; coût estimé ; qualité narrative non jugée (la variante est écartée avant).
