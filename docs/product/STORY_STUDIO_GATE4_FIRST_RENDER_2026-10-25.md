# Story Studio — premier rendu complet de 100 s (essai du 2026-10-25)

Histoire : « La ville sans mots » (scénario 3 du Gate 1, fixture `story_v21_ville_sans_mots.json`, contrat v2.1). Exécutée **en local** par `experiments/story_writing/run_local_story.py` à travers le vrai pipeline (contrat, voix, chronologie, plan de scènes, rig Godot, mixage, contrôle qualité). **Aucun crédit Faceloop, aucune écriture en base ni en stockage, aucun déploiement.** Autorisation explicite de l'utilisateur pour l'unique appel payant (voix ElevenLabs, plafond 2 000 caractères).

## 1. Dépense
| Poste | Mesure |
| --- | --- |
| ElevenLabs | 16 requêtes, **1 513 caractères** envoyés (plafond 2 000), 0 ligne depuis le cache ; quota du forfait Creator lu avant l'essai : 30 537 / 121 032 caractères (aucune extension payante possible, donc pas de surfacturation) |
| Coût estimé | ≈ 0,27 $ à 0,18 $ / 1 000 caractères ; réellement imputé au quota prépayé |
| Autres | rendu Godot et mixage locaux (0 €) ; aucune API OpenAI ni Anthropic |

## 2. Mesures du fichier final (ffprobe / mesure du moteur)
- Durée **100,25 s** (cible 90 s ; bande tolérée 76,5 à 108 s : dans la bande) ; audio 100,21 s ; écart image/son 0,04 s.
- 1080×1920, 24 i/s, image et son présents ; **36,2 Mio**.
- Volume moyen −17,1 dB, crête −1,3 dB (aucun écrêtage). Contrôle qualité : **0 problème bloquant, 0 à revoir**.
- Débit de parole réel : narrateur **15,0**, Rosette 16,6, Pip 20,0, ensemble **16,5 caractères/s**. Les estimations du contrat (92 s au débit rapide, 111 s au débit lent) encadraient bien la durée réelle (100 s).
- Part de narration : 55 % de la parole (51 s sur 92 s).

## 3. Ce que montrent les images (planche de 16 vues, une toutes les 6,5 s)
**Fonctionne** : 16 plans, décors boutique et rue en alternance, sous-titres synchronisés et lisibles, gros plans de Rosette et Pip, narrateur représenté par les deux personnages à l'écoute, aucun plan noir ni figé détecté.
**Défauts constatés** :
1. **Monotonie des passages narrés** : pendant 51 s, les mêmes deux personnages restent debout dans le même cadre de rue ou de boutique, presque immobiles. C'est le principal risque de rétention : rien n'est montré de ce que le narrateur raconte.
2. **`clutch_head` de Pip** : les deux gants couvrent ses lunettes et ses yeux pendant une réplique entière.
3. **Dans la rue, la mise en scène des personnages est identique d'un plan à l'autre** (même placement, même pose d'écoute).
4. **Taille du fichier** : 36,2 Mio pour 100 s, la limite du contrôle qualité est de 40 Mio ; une histoire de 120 à 180 s la dépasserait.

## 4. Ce que cet essai ne prouve pas
Le son n'a pas été écouté par l'auteur de ce rapport : l'intelligibilité, le naturel des trois voix et la justesse du lip-sync sont **non vérifiés** (seuls les chiffres de durée et de volume le sont). La qualité narrative et artistique reste à juger par l'utilisateur ; aucune donnée d'audience.

## 5. Critères du brief (§8)
| Critère | État |
| --- | --- |
| Vidéo ≥ 60 s mesurée sur le fichier | **OK** (100,25 s) |
| Dans la tolérance autour de la cible | **OK** (bande 76,5-108 s) |
| Audio présent, sans coupure | présent ; coupures non écoutées |
| Sous-titres synchronisés, sans débordement | OK sur l'échantillon d'images |
| Pas de plan noir inattendu | OK (contrôle automatique) |
| Pipeline reproductible en local, coût externe | OK ; coût externe non nul : ≈ 0,27 $ de voix (objectif 0 € atteignable seulement avec une voix locale) |
| Qualité artistique approuvée | **en attente de l'utilisateur** |
| Tests CI et rendu Linux | tests verts ; **rendu Linux de ce scénario non lancé** |

## 6. Suite proposée (Gate 3, ordre de priorité)
1. **Varier ce qui est montré pendant la narration** : mouvements de caméra, plans d'insertion (objets, mots, écriteaux), personnages qui changent de pose et de place, fond animé ; sans cela, un récit de plus de 60 s perd le spectateur.
2. Corriger `clutch_head` (mains au-dessus de la tête, pas devant les yeux).
3. Relever la limite de taille ou baisser le débit d'encodage pour les durées de 120 à 180 s.
4. Faire écouter la vidéo à l'utilisateur avant toute autre dépense de voix ; garder le cache (`voice_cache`) pour retoucher l'image sans repayer l'audio.
