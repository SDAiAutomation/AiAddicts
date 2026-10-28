# Story Studio — clips clés image→vidéo (2026-10-28)

Statut : **module autonome, désactivé par défaut, non branché** au worker ni au renderer. Code : `growthos/engine/story_animation/key_clips.py` (`story-key-clips:v1`, prompt `key-clip-motion:v1`). Tests hors ligne : `test_key_clips.py`.

## Pourquoi

Les références (Gate 0 §3) montrent du jeu de corps complet sur quelques moments clés. Le renderer « storyboard » (une image IA par beat de 2–4 s avec mouvement de caméra) couvre le reste. Ce module transforme les 3–5 beats qui ont le plus besoin de mouvement en clips courts image→vidéo ; tous les autres beats gardent leur image fixe.

## Fonctionnement

1. `select_key_beats(beats, max_clips, max_total_s)` : choix déterministe. Drapeau explicite `motion=True` d'abord (`False` exclut), puis score : intention (climax > conflit > action > révélation) et verbes d'action FR/EN dans la description ou le texte. Exclus : score nul, pas d'image, id invalide, beat de moins de 1,5 s. Plafonds : 5 clips, 18 s demandées au total.
2. `build_motion_prompt(beat)` : action tirée de la description, style rubber hose N&B années 1930, identité des personnages conservée, accent rouge unique, aucun texte, consigne caméra (plan fixe pour l'action, travelling avant pour climax/révélation).
3. `make_key_clips(beats, provider, budget, out_dir=...)` : un appel par beat, une seule reprise, délai maximal, validation ffprobe/ffmpeg (durée, 9:16 et largeur ≥ 480, pas noir, pas figé à plus de 50 %). Tout échec donne `None` pour ce beat : le renderer garde l'image fixe. Le rapport (`to_dict()`) trace version, fournisseur, modèle, tentatives, latence, erreurs et coûts.

Forme du beat attendue (`Beat`) : `id, start, end, text, intent, description, image_path, motion`. Le renderer adapte ses beats à cette forme ; le module ne lit aucun autre contrat.

## Activer

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `STORY_KEY_CLIP_PROVIDER` | vide = désactivé | `fake` (local, gratuit), `veo`, `seedance`, `wan` (stubs) |
| `STORY_KEY_CLIP_MAX_USD` | 1.5 | plafond dur par histoire (borné à 10) |
| `STORY_KEY_CLIP_MAX_CLIPS` | 4 | 0 à 5 |
| `STORY_KEY_CLIP_TIMEOUT_S` | 300 | délai par tentative |
| `STORY_KEY_CLIP_USD_PER_S` | aucun | tarif par seconde, prioritaire sur celui du fournisseur |

`fake` produit un lent zoom ffmpeg sur l'image : il sert à tester la chaîne de bout en bout sans réseau, pas à juger un rendu.

## Modèle de coût

- Estimation par tentative = secondes demandées × tarif par seconde. Secondes demandées = durée du beat arrondie à la seconde supérieure, entre 2 et 5 s.
- Coût réel = ce que le fournisseur déclare. **Absent = inconnu (`None`), jamais 0** ; le total réel du rapport vaut `None` dès qu'une tentative n'a pas de mesure.
- Plafond : avant **chaque** tentative, reprises comprises, on vérifie dépense engagée + estimation ≤ plafond. Dépense engagée = coût réel s'il est connu, sinon estimation (un appel en échec ou expiré peut être facturé).
- Sans tarif connu (fournisseur ou variable), aucun appel : le plafond ne pourrait pas être garanti (`rate_unknown`).
- Ordre de grandeur : 4 clips de 3–4 s ≈ 14 s ; à 0,10 $/s environ 1,40 $ sans reprise. **Ce tarif est un exemple, pas un prix constaté.**

## Décision laissée au propriétaire

**Quel fournisseur image→vidéo.** `veo`, `seedance` et `wan` lèvent `NotConfigured` : aucun endpoint, nom de clé ni tarif n'est supposé. Pour en activer un, il faut choisir le fournisseur, sa clé (côté serveur), son tarif réel par seconde, puis implémenter son transport (soumission, attente, téléchargement local du MP4, coût déclaré), testé avec un transport factice. Critères à comparer sur un même jeu de beats : tenue de l'identité et de l'accent rouge, jeu de corps, absence de texte parasite, prix par seconde, latence.

## Limites connues

- Le délai rend la main au bout du temps imparti, mais ne peut pas tuer un appel bloquant : le transport réel doit lui-même respecter `timeout_s`.
- La validation ne juge pas l'art (dérive de personnage, membres fusionnés) : jugement humain ou `render-checker`.
- Le choix des beats est un classement par mots-clés, pas une compréhension de l'histoire ; le drapeau `motion` de la direction permet de le corriger.
