# Moteur de génération — Faceless Kids Stories

Moteur minimal : script → voix off → vidéo → montage final.
Base du futur clone de FacelessReels / de ton outil clone-Blotato.

## Installation

```bash
pip install -r requirements.txt --break-system-packages
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

## API asynchrone (FastAPI)

En plus du CLI bloquant, une API expose le pipeline en jobs asynchrones (queue en mémoire,
un job traité à la fois par un worker en arrière-plan) :

```bash
uvicorn api:app --reload
```

| Endpoint            | Description                                      |
|----------------------|---------------------------------------------------|
| `GET /health`         | Vérifie que l'API répond                          |
| `GET /stories`         | Liste les scripts disponibles dans `stories/`       |
| `POST /jobs`            | Lance une génération (`{"story_path": "stories/histoire-01.json"}`), retourne le job créé |
| `GET /jobs`              | Liste tous les jobs et leur statut                  |
| `GET /jobs/{job_id}`      | Statut détaillé d'un job (étape en cours, résultat, erreur) |

Un job passe par les statuts `pending` → `running` → `completed`/`failed`. Le champ `step`
(`voiceover`, `video`, `assembly`, `done`) et `detail` permettent de suivre la progression bloc par
bloc sans bloquer la requête HTTP. La documentation interactive est disponible sur `/docs` une fois
le serveur lancé.

Limite actuelle : le registre des jobs est en mémoire (perdu au redémarrage du process) et un seul
job est traité à la fois — cohérent avec la limite « pas de parallélisation » ci-dessous, à revoir
si le volume augmente (ex. remplacer par Redis + plusieurs workers).

## Structure du projet

```
faceless-kids-stories/
├── main.py                  # CLI (appelle engine.pipeline directement)
├── api.py                   # API FastAPI (jobs asynchrones, appelle engine.pipeline via un worker)
├── engine/
│   ├── story.py              # chargement + validation des scripts JSON
│   ├── tts.py                 # voix off (ElevenLabs)
│   ├── video.py                # clips vidéo (Wan 2.2 via fal.ai)
│   ├── subtitles.py             # génération des sous-titres SRT
│   ├── assembler.py              # montage final (ffmpeg)
│   ├── pipeline.py                # orchestration complète (partagée CLI + API)
│   ├── jobs.py                     # registre des jobs en mémoire (JobStore)
│   └── worker.py                    # worker en arrière-plan (file de jobs)
├── stories/                 # scripts d'histoires (*.json)
├── output/                  # audio/, video_clips/, final/ (généré, ignoré par git)
└── tests/                   # tests unitaires (logique pure + API mockée, sans appel réseau réel)
```

## Tests

```bash
python -m unittest discover -s tests
```

Les tests couvrent la validation des scripts d'histoire, la génération des sous-titres et le cycle
de vie complet des jobs API (avec `engine.pipeline.generate_story` mocké) ; aucun appel réseau réel
n'est effectué, pas besoin de clés API pour les lancer.

## Prochaines étapes (vers le clone FacelessReels complet)

1. **Tester ce moteur en CLI** sur "Le Petit Hibou Courageux" — valider qualité/coût réels
   (bloqué en l'absence de clés ElevenLabs/fal.ai valides dans cet environnement ; le pipeline
   est prêt, il suffit de configurer `.env` et de lancer `python main.py stories/histoire-01.json`)
2. **Wrapper en API** (FastAPI) — génération asynchrone (job queue), au lieu d'un script bloquant ✅ fait
3. **Scheduler** — génération X heures avant publication programmée
4. **Publisher multi-plateforme** — brancher ton clone Blotato pour la diffusion auto TikTok/YouTube/Instagram
5. **Frontend wizard** — formulaire multi-étapes (nom de série, niche, voix, durée, planning) comme vu sur FacelessReels

## Limites actuelles de ce moteur (à savoir avant de lancer)

- Pas de gestion d'erreur avancée (retry automatique) — à ajouter avant usage en production
- Un seul appel séquentiel par bloc — pas de parallélisation (à optimiser pour réduire le temps total)
- Le style visuel est simple (un prompt texte) — pas de gestion d'un personnage 100% cohérent visuellement d'un bloc à l'autre (Wan 2.2 n'a pas de "character reference" natif comme certains modèles premium)
