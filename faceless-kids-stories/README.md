# Moteur de génération — Faceless Kids Stories

Moteur minimal : script → voix off → vidéo → montage final.
Base du futur clone de FacelessReels / de ton outil clone-Blotato.

## Installation

```bash
pip install requests --break-system-packages
# ffmpeg doit être installé sur la machine (apt install ffmpeg / brew install ffmpeg)
```

## Configuration

```bash
export ELEVENLABS_API_KEY="ta_clé_elevenlabs"
export FAL_KEY="ta_clé_fal_ai"
```

- ElevenLabs : compte + clé sur elevenlabs.io (Profile → API Keys)
- fal.ai : compte + clé sur fal.ai (Dashboard → Keys) — paiement à l'usage, pas d'abonnement

## Lancer une génération complète

```bash
python main.py stories/histoire-01.json
```

Ça génère, dans l'ordre :
1. `output/audio/` — un mp3 par bloc (voix Celine)
2. `output/video_clips/` — un mp4 par bloc (style Studio 3D, Wan 2.2)
3. `output/final/` — la vidéo assemblée avec sous-titres incrustés

## Coût estimé (histoire de 90s, 9 blocs)

- Vidéo (Wan 2.2, 720p, fal.ai) : ~0,08$/s × 90s ≈ **7,20$**
- Voix off (ElevenLabs) : selon ton forfait (le tier gratuit couvre ~10 min/mois)
- Total par histoire : **~7-8$**, sans abonnement — tu ne paies que ce que tu génères

## Structure d'un script d'histoire (`stories/*.json`)

Chaque histoire est un fichier JSON avec :
- `title`, `theme`, `voice_id`, `aspect_ratio`, `style_prompt`
- `blocks` : liste de blocs, chacun avec `vo` (texte narré) et `visual` (description de la scène)

C'est ce format que tu réutilises pour écrire une nouvelle histoire — pas besoin de toucher au code.

Un exemple complet est fourni dans `stories/histoire-01.json` ("Le Petit Hibou Courageux", 9 blocs).
Avant de lancer une génération, remplace `voice_id` par l'ID réel de ta voix ElevenLabs (ex. Celine).

## Structure du projet

```
faceless-kids-stories/
├── main.py                  # orchestrateur CLI
├── engine/
│   ├── story.py              # chargement + validation des scripts JSON
│   ├── tts.py                 # voix off (ElevenLabs)
│   ├── video.py                # clips vidéo (Wan 2.2 via fal.ai)
│   ├── subtitles.py             # génération des sous-titres SRT
│   └── assembler.py              # montage final (ffmpeg)
├── stories/                 # scripts d'histoires (*.json)
├── output/                  # audio/, video_clips/, final/ (généré, ignoré par git)
└── tests/                   # tests unitaires (logique pure, sans appel API)
```

## Tests

```bash
python -m unittest discover -s tests
```

Les tests couvrent la validation des scripts d'histoire et la génération des sous-titres ;
ils ne font aucun appel réseau (pas besoin de clés API pour les lancer).

## Prochaines étapes (vers le clone FacelessReels complet)

1. **Tester ce moteur en CLI** sur "Le Petit Hibou Courageux" — valider qualité/coût réels
2. **Wrapper en API** (FastAPI) — génération asynchrone (job queue), au lieu d'un script bloquant
3. **Scheduler** — génération X heures avant publication programmée
4. **Publisher multi-plateforme** — brancher ton clone Blotato pour la diffusion auto TikTok/YouTube/Instagram
5. **Frontend wizard** — formulaire multi-étapes (nom de série, niche, voix, durée, planning) comme vu sur FacelessReels

## Limites actuelles de ce moteur (à savoir avant de lancer)

- Pas de gestion d'erreur avancée (retry automatique) — à ajouter avant usage en production
- Un seul appel séquentiel par bloc — pas de parallélisation (à optimiser pour réduire le temps total)
- Le style visuel est simple (un prompt texte) — pas de gestion d'un personnage 100% cohérent visuellement d'un bloc à l'autre (Wan 2.2 n'a pas de "character reference" natif comme certains modèles premium)
